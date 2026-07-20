#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize Project 05 dual-board required/target overlap."
    )
    parser.add_argument("--group-run-id", required=True)
    parser.add_argument("--tier", required=True, choices=["required", "target"])
    parser.add_argument("--jetson-stability", required=True, type=Path)
    parser.add_argument("--rk3588-stability", required=True, type=Path)
    parser.add_argument("--jetson-run-id", default=None)
    parser.add_argument("--rk3588-run-id", default=None)
    parser.add_argument("--input-source-id", default="video_set_runtime_v1")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def load_first_jsonl_row(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path}:{line_no}: row must be object")
            return row
    raise SystemExit(f"{path}: input has no JSONL rows")


def parse_iso8601(value: str, field_name: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"invalid {field_name}: {value}") from exc


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_number(row: dict[str, Any], key: str, label: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)):
        raise SystemExit(f"{label}: {key} must be number, got {value!r}")
    return float(value)


def require_bool(row: dict[str, Any], key: str, label: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise SystemExit(f"{label}: {key} must be boolean, got {value!r}")
    return value


def summarize_board(label: str, run_id: str | None, row: dict[str, Any]) -> dict[str, Any]:
    timestamp = row.get("timestamp")
    if not isinstance(timestamp, str):
        raise SystemExit(f"{label}: timestamp must be string")
    end_utc = parse_iso8601(timestamp, f"{label}.timestamp")
    window_sec = require_number(row, "window_sec", label)
    start_utc = end_utc - timedelta(seconds=window_sec)
    return {
        "run_id": run_id or row.get("run_id"),
        "board": row.get("board"),
        "target": row.get("target"),
        "input_source_id": row.get("input_source_id"),
        "stability_tier": row.get("stability_tier"),
        "requested_window_sec": row.get("requested_window_sec"),
        "window_sec": window_sec,
        "window_requirement_met": require_bool(row, "window_requirement_met", label),
        "detection_fps": row.get("detection_fps"),
        "event_count": row.get("event_count"),
        "alarm_count": row.get("alarm_count"),
        "llm_call_count": row.get("llm_call_count"),
        "vlm_call_count": row.get("vlm_call_count"),
        "drop_count": row.get("drop_count"),
        "status": row.get("status"),
        "service_status": row.get("service_status"),
        "monitor_log_path": row.get("monitor_log_path"),
        "runtime_log_path": row.get("runtime_log_path"),
        "start_utc": start_utc,
        "end_utc": end_utc,
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    jetson_row = load_first_jsonl_row(args.jetson_stability)
    rk_row = load_first_jsonl_row(args.rk3588_stability)

    jetson = summarize_board("jetson", args.jetson_run_id, jetson_row)
    rk3588 = summarize_board("rk3588", args.rk3588_run_id, rk_row)

    overlap_start = max(jetson["start_utc"], rk3588["start_utc"])
    overlap_end = min(jetson["end_utc"], rk3588["end_utc"])
    overlap_sec = max(0.0, (overlap_end - overlap_start).total_seconds())
    start_skew_sec = abs((jetson["start_utc"] - rk3588["start_utc"]).total_seconds())

    if args.tier == "required":
        expected_window_sec = 1800.0
        min_overlap_sec = 1500.0
        aggregate_ready = "dual_board_required_ready"
    else:
        expected_window_sec = 7200.0
        min_overlap_sec = 6900.0
        aggregate_ready = "dual_board_target_ready"

    jetson_gate_pass = (
        jetson["stability_tier"] == args.tier
        and float(jetson["requested_window_sec"] or 0.0) == expected_window_sec
        and jetson["window_requirement_met"] is True
        and jetson["drop_count"] == 0
        and jetson["input_source_id"] == args.input_source_id
    )
    rk_gate_pass = (
        rk3588["stability_tier"] == args.tier
        and float(rk3588["requested_window_sec"] or 0.0) == expected_window_sec
        and rk3588["window_requirement_met"] is True
        and rk3588["drop_count"] == 0
        and rk3588["input_source_id"] == args.input_source_id
    )
    overlap_gate_pass = start_skew_sec <= 300.0 and overlap_sec >= min_overlap_sec

    if jetson_gate_pass and rk_gate_pass and overlap_gate_pass:
        aggregate_status = aggregate_ready
    elif jetson["window_requirement_met"] and rk3588["window_requirement_met"]:
        aggregate_status = "degraded"
    else:
        aggregate_status = "failed"

    return {
        "group_run_id": args.group_run_id,
        "tier": args.tier,
        "input_source_id": args.input_source_id,
        "jetson_run_id": jetson["run_id"],
        "rk3588_run_id": rk3588["run_id"],
        "jetson_start_utc": iso_z(jetson["start_utc"]),
        "jetson_end_utc": iso_z(jetson["end_utc"]),
        "rk_start_utc": iso_z(rk3588["start_utc"]),
        "rk_end_utc": iso_z(rk3588["end_utc"]),
        "start_skew_sec": round(start_skew_sec, 3),
        "window_overlap_sec": round(overlap_sec, 3),
        "required_window_sec": expected_window_sec,
        "required_overlap_sec": min_overlap_sec,
        "jetson_gate_pass": jetson_gate_pass,
        "rk3588_gate_pass": rk_gate_pass,
        "overlap_gate_pass": overlap_gate_pass,
        "aggregate_status": aggregate_status,
        "jetson": {
            "run_id": jetson["run_id"],
            "stability_tier": jetson["stability_tier"],
            "requested_window_sec": jetson["requested_window_sec"],
            "window_sec": jetson["window_sec"],
            "window_requirement_met": jetson["window_requirement_met"],
            "detection_fps": jetson["detection_fps"],
            "event_count": jetson["event_count"],
            "alarm_count": jetson["alarm_count"],
            "llm_call_count": jetson["llm_call_count"],
            "vlm_call_count": jetson["vlm_call_count"],
            "drop_count": jetson["drop_count"],
            "status": jetson["status"],
            "service_status": jetson["service_status"],
            "monitor_log_path": jetson["monitor_log_path"],
            "runtime_log_path": jetson["runtime_log_path"],
        },
        "rk3588": {
            "run_id": rk3588["run_id"],
            "stability_tier": rk3588["stability_tier"],
            "requested_window_sec": rk3588["requested_window_sec"],
            "window_sec": rk3588["window_sec"],
            "window_requirement_met": rk3588["window_requirement_met"],
            "detection_fps": rk3588["detection_fps"],
            "event_count": rk3588["event_count"],
            "alarm_count": rk3588["alarm_count"],
            "llm_call_count": rk3588["llm_call_count"],
            "vlm_call_count": rk3588["vlm_call_count"],
            "drop_count": rk3588["drop_count"],
            "status": rk3588["status"],
            "service_status": rk3588["service_status"],
            "monitor_log_path": rk3588["monitor_log_path"],
            "runtime_log_path": rk3588["runtime_log_path"],
        },
    }


def render_markdown(summary: dict[str, Any], jetson_path: Path, rk_path: Path) -> str:
    lines = [
        "# Project 05 dual-board summary",
        "",
        f"- group_run_id: `{summary['group_run_id']}`",
        f"- tier: `{summary['tier']}`",
        f"- input_source_id: `{summary['input_source_id']}`",
        f"- jetson_stability: `{jetson_path}`",
        f"- rk3588_stability: `{rk_path}`",
        f"- aggregate_status: `{summary['aggregate_status']}`",
        f"- start_skew_sec: {summary['start_skew_sec']}",
        f"- window_overlap_sec: {summary['window_overlap_sec']}",
        f"- required_window_sec: {summary['required_window_sec']}",
        f"- required_overlap_sec: {summary['required_overlap_sec']}",
        "",
        "## Boards",
        "",
        "| board | run_id | tier | requested_window_sec | window_sec | window_requirement_met | detection_fps | event_count | alarm_count | llm_call_count | vlm_call_count | drop_count | gate_pass |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|",
        f"| Jetson 8GB | `{summary['jetson']['run_id']}` | `{summary['jetson']['stability_tier']}` | {summary['jetson']['requested_window_sec']} | {summary['jetson']['window_sec']} | {summary['jetson']['window_requirement_met']} | {summary['jetson']['detection_fps']} | {summary['jetson']['event_count']} | {summary['jetson']['alarm_count']} | {summary['jetson']['llm_call_count']} | {summary['jetson']['vlm_call_count']} | {summary['jetson']['drop_count']} | `{summary['jetson_gate_pass']}` |",
        f"| RK3588 8GB | `{summary['rk3588']['run_id']}` | `{summary['rk3588']['stability_tier']}` | {summary['rk3588']['requested_window_sec']} | {summary['rk3588']['window_sec']} | {summary['rk3588']['window_requirement_met']} | {summary['rk3588']['detection_fps']} | {summary['rk3588']['event_count']} | {summary['rk3588']['alarm_count']} | {summary['rk3588']['llm_call_count']} | {summary['rk3588']['vlm_call_count']} | {summary['rk3588']['drop_count']} | `{summary['rk3588_gate_pass']}` |",
        "",
        "## Window",
        "",
        f"- jetson_start_utc: `{summary['jetson_start_utc']}`",
        f"- jetson_end_utc: `{summary['jetson_end_utc']}`",
        f"- rk_start_utc: `{summary['rk_start_utc']}`",
        f"- rk_end_utc: `{summary['rk_end_utc']}`",
        f"- overlap_gate_pass: `{summary['overlap_gate_pass']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    summary = build_summary(args)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(
            render_markdown(summary, args.jetson_stability, args.rk3588_stability),
            encoding="utf-8",
        )
    if not args.output_json and not args.output_md:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"aggregate_status={summary['aggregate_status']}")
        print(f"start_skew_sec={summary['start_skew_sec']}")
        print(f"window_overlap_sec={summary['window_overlap_sec']}")
        if args.output_json:
            print(f"output_json={args.output_json}")
        if args.output_md:
            print(f"output_md={args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
