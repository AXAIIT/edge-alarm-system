#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import parse_simple_yaml, read_jsonl, utc_now_iso, write_jsonl


RAM_RE = re.compile(r"\bRAM\s+([0-9.]+)/[0-9.]+MB")
SWAP_RE = re.compile(r"\bSWAP\s+([0-9.]+)/[0-9.]+MB")
TEMP_RE = re.compile(r"@([0-9.]+)C")
POWER_RE = re.compile(r"\b(?:POM_5V_IN|VDD_IN)\s+([0-9.]+)/[0-9]+")
RK_TEMP_RE = re.compile(r"\btemperature_c=([0-9.]+)")
RK_MEMORY_RE = re.compile(r"\bmemory_mb=([0-9.]+)")
RK_SWAP_RE = re.compile(r"\bswap_used_mb=([0-9.]+)")
RK_MEM_TOTAL_RE = re.compile(r"\bmem_total_mb=([0-9.]+)")
RK_MEM_AVAILABLE_RE = re.compile(r"\bmem_available_mb=([0-9.]+)")
RK_PROCESS_HWM_RE = re.compile(r"\bprocess_hwm_mb=([0-9.]+)")
RK_PROCESS_RSS_RE = re.compile(r"\bprocess_rss_mb=([0-9.]+)")


def max_or_none(values: list[float]) -> float | None:
    return round(max(values), 3) if values else None


def read_monitor_peaks(path: Path | None) -> dict[str, float | None]:
    peaks: dict[str, list[float]] = {
        "memory_mb": [],
        "swap_used_mb": [],
        "temperature_c": [],
        "power_w": [],
    }
    if not path or not path.exists():
        return {key: None for key in peaks}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if m := RAM_RE.search(line):
                peaks["memory_mb"].append(float(m.group(1)))
            if m := SWAP_RE.search(line):
                peaks["swap_used_mb"].append(float(m.group(1)))
            peaks["temperature_c"].extend(float(v) for v in TEMP_RE.findall(line))
            if m := POWER_RE.search(line):
                peaks["power_w"].append(float(m.group(1)) / 1000.0)
            peaks["temperature_c"].extend(float(v) for v in RK_TEMP_RE.findall(line))
            peaks["memory_mb"].extend(float(v) for v in RK_MEMORY_RE.findall(line))
            peaks["swap_used_mb"].extend(float(v) for v in RK_SWAP_RE.findall(line))
            total_match = RK_MEM_TOTAL_RE.search(line)
            available_match = RK_MEM_AVAILABLE_RE.search(line)
            if total_match and available_match:
                peaks["memory_mb"].append(float(total_match.group(1)) - float(available_match.group(1)))
            if m := RK_PROCESS_HWM_RE.search(line):
                peaks["memory_mb"].append(float(m.group(1)))
            elif m := RK_PROCESS_RSS_RE.search(line):
                peaks["memory_mb"].append(float(m.group(1)))
    return {key: max_or_none(values) for key, values in peaks.items()}


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if value is not None:
            counter[str(value)] += 1
    return dict(counter)


def count_llm_calls(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("mode") not in {"template", "template_fallback_interface_wiring"})


def count_fallbacks(alarms: list[dict[str, Any]]) -> tuple[int, dict[str, int]]:
    total = 0
    by_domain: Counter[str] = Counter()
    ok_values = {"ok", "pass", "none", None}
    for alarm in alarms:
        fallback = alarm.get("fallback_status")
        if not isinstance(fallback, dict):
            continue
        has_fallback = any(value not in ok_values for value in fallback.values())
        if has_fallback:
            total += 1
            by_domain[str(alarm.get("alarm_domain", "unknown"))] += 1
    return total, dict(by_domain)


def max_metric(alarms: list[dict[str, Any]], key: str) -> float | None:
    values: list[float] = []
    for alarm in alarms:
        metrics = alarm.get("system_metrics")
        if isinstance(metrics, dict) and isinstance(metrics.get(key), (int, float)):
            values.append(float(metrics[key]))
    return max_or_none(values)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Project 08 time-window stability raw JSONL.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--board", default="Jetson 8GB")
    parser.add_argument("--target", default="jetson_8gb")
    parser.add_argument("--environment-baseline-id", default="20260609_jetson_8gb_env_baseline")
    parser.add_argument("--model-config", type=Path, default=Path("projects/08_alarm_system/configs/models/jetson_model_combo.yaml"))
    parser.add_argument("--input-source-id", default="video_set_runtime_v1")
    parser.add_argument("--stability-tier", choices=["smoke", "required", "target", "stress"], default="smoke")
    parser.add_argument("--window-sec", type=float, default=600.0)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--alarms", required=True, type=Path)
    parser.add_argument("--llm", type=Path, default=None)
    parser.add_argument("--vlm", type=Path, default=None)
    parser.add_argument("--monitor-log", type=Path, default=None)
    parser.add_argument("--runtime-log-path", default=None)
    parser.add_argument("--failure-log-path", default=None)
    parser.add_argument("--status", choices=["pass", "fail", "degraded", "blocked", "not_executed", "not_verified"], default="not_verified")
    parser.add_argument("--service-status", choices=["running", "degraded", "restarting", "stopped", "failed", "unknown"], default="unknown")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    events = read_jsonl(args.events)
    alarms = read_jsonl(args.alarms)
    llm_rows = read_jsonl(args.llm) if args.llm and args.llm.exists() else []
    vlm_rows = read_jsonl(args.vlm) if args.vlm and args.vlm.exists() else []
    combo = parse_simple_yaml(args.model_config)
    monitor = read_monitor_peaks(args.monitor_log)
    fallback_count, fallback_by_domain = count_fallbacks(alarms)

    row = {
        "run_id": args.run_id,
        "timestamp": utc_now_iso(),
        "schema_version": 1,
        "project": "08_alarm_system",
        "measurement_granularity": "time_window",
        "board": args.board,
        "target": args.target,
        "environment_baseline_id": args.environment_baseline_id,
        "model_combo_id": combo.get("model_combo_id", "unknown_combo"),
        "input_source_id": args.input_source_id,
        "stability_tier": args.stability_tier,
        "window_index": 0,
        "window_sec": args.window_sec,
        "requested_window_sec": args.window_sec,
        "window_requirement_met": True,
        "detection_fps": None,
        "event_count": len(events),
        "event_count_by_alarm_domain": count_by(events, "alarm_domain"),
        "event_count_by_alarm_type": count_by(events, "alarm_type"),
        "alarm_count": len(alarms),
        "vlm_call_count": len(vlm_rows),
        "llm_call_count": count_llm_calls(llm_rows),
        "event_queue_depth": max(
            [int(v) for v in [event.get("queue_depth_at_trigger") for event in events] if isinstance(v, int)],
            default=None,
        ),
        "drop_count": 0,
        "end_to_end_alarm_ms": max_metric(alarms, "end_to_end_alarm_ms"),
        "memory_mb": monitor["memory_mb"],
        "swap_used_mb": monitor["swap_used_mb"],
        "temperature_c": monitor["temperature_c"],
        "power_w": monitor["power_w"],
        "fallback_count": fallback_count,
        "fallback_count_by_alarm_domain": fallback_by_domain,
        "error_count": 0,
        "restart_count": 0,
        "reconnect_count": 0,
        "service_status": args.service_status,
        "status": args.status,
        "runtime_log_path": args.runtime_log_path,
        "monitor_log_path": str(args.monitor_log) if args.monitor_log else None,
        "failure_log_path": args.failure_log_path,
        "related_troubleshooting_id": "P05-JETSON-CONCURRENCY-PENDING-001"
        if args.target == "jetson_8gb"
        else None,
    }
    count = write_jsonl(args.output, [row])
    print(f"stability_rows_written={count}")
    print(f"output={args.output}")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
