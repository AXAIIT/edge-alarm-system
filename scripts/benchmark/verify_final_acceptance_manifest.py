#!/usr/bin/env python3
"""Verify and freeze the selected Project 05 final-acceptance evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_GROUP_SUMMARY = Path(
    "benchmark/processed/05_alarm_system/20260717_p05_dual_board_target_v1_dual_board_summary.json"
)
DEFAULT_TEXT_RUN_ID = "20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3"
DEFAULT_OUTPUT_JSON = Path("benchmark/processed/05_alarm_system/project05_final_acceptance_manifest.json")
DEFAULT_OUTPUT_MD = Path("benchmark/processed/05_alarm_system/project05_final_acceptance_manifest.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-summary", type=Path, default=DEFAULT_GROUP_SUMMARY)
    parser.add_argument("--text-run-id", default=DEFAULT_TEXT_RUN_ID)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return path.as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"final acceptance verification failed: {message}")


def schema_pass(path: Path) -> bool:
    return "status: pass" in path.read_text(encoding="utf-8")


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def main() -> int:
    args = parse_args()
    group = read_json(args.group_summary)
    require(group.get("aggregate_status") == "dual_board_target_ready", "dual-board aggregate status")
    require(all(group.get(key) is True for key in ("jetson_gate_pass", "rk3588_gate_pass", "overlap_gate_pass")), "target gates")
    require(float(group["window_overlap_sec"]) >= float(group["required_overlap_sec"]), "target overlap")

    for board_key in ("jetson", "rk3588"):
        row = group[board_key]
        require(row.get("window_requirement_met") is True, f"{board_key} window requirement")
        require(float(row.get("drop_count", -1)) == 0.0, f"{board_key} drop count")
        require(int(row.get("event_count", -1)) == int(row.get("alarm_count", -2)), f"{board_key} event/alarm count")

    group_run_id = str(group["group_run_id"])
    processed_root = Path("benchmark/processed/05_alarm_system")
    target_evidence = {
        "jetson": {
            "root": Path("benchmark/raw/05_alarm_system/jetson_8gb"),
            "run_id": str(group["jetson_run_id"]),
            "schema_checks": [
                processed_root / f"{group_run_id}_jetson_resident_event_schema_check.md",
                processed_root / f"{group_run_id}_jetson_resident_alarm_schema_check.md",
                processed_root / f"{group_run_id}_jetson_resident_raw_schema_check.md",
                processed_root / f"{group_run_id}_jetson_resident_stability_schema_check.md",
                processed_root / f"{group_run_id}_jetson_async_alarm_schema_check.md",
                processed_root / f"{group_run_id}_jetson_async_benchmark_schema_check.md",
            ],
        },
        "rk3588": {
            "root": Path("benchmark/raw/05_alarm_system/rk3588_8gb"),
            "run_id": str(group["rk3588_run_id"]),
            "schema_checks": [
                processed_root / f"{group_run_id}_rk3588_resident_target_event_schema_check.md",
                processed_root / f"{group_run_id}_rk3588_resident_target_alarm_schema_check.md",
                processed_root / f"{group_run_id}_rk3588_resident_target_raw_schema_check.md",
                processed_root / f"{group_run_id}_rk3588_resident_target_stability_schema_check.md",
            ],
        },
    }
    target_paths: list[Path] = []
    for board_key, evidence in target_evidence.items():
        root = evidence["root"]
        run_id = evidence["run_id"]
        events_path = root / "events" / f"{run_id}_events.jsonl"
        alarms_path = root / "alarms" / f"{run_id}_alarms.jsonl"
        stability_path = root / f"{run_id}_alarm_system_stability.jsonl"
        require(events_path.is_file() and alarms_path.is_file() and stability_path.is_file(), f"{board_key} target raw evidence")
        expected = int(group[board_key]["event_count"])
        require(line_count(events_path) == expected, f"{board_key} target event row count")
        require(line_count(alarms_path) == expected, f"{board_key} target alarm row count")
        require(all(path.is_file() and schema_pass(path) for path in evidence["schema_checks"]), f"{board_key} target schema checks")
        target_paths.extend([events_path, alarms_path, stability_path, *evidence["schema_checks"]])

    code_boundary_path = processed_root / "project5_code_boundary_check.md"
    require(code_boundary_path.is_file(), "Project5 code-boundary report")
    code_boundary_text = code_boundary_path.read_text(encoding="utf-8")
    require(
        "code_boundary_status: `independent_runtime_pass`" in code_boundary_text
        or "code_boundary_status=independent_runtime_pass" in code_boundary_text,
        "Project5 code boundary",
    )

    board = "jetson_8gb"
    run_id = args.text_run_id
    raw_root = Path("benchmark/raw/05_alarm_system") / board
    llm_path = raw_root / f"{run_id}_llm_outputs.jsonl"
    alarm_path = raw_root / "alarms" / f"{run_id}_alarms.jsonl"
    stability_path = raw_root / f"{run_id}_alarm_system_stability.jsonl"
    schema_paths = [
        processed_root / f"{run_id}_event_package_schema_check.md",
        processed_root / f"{run_id}_alarm_json_schema_check.md",
        processed_root / f"{run_id}_alarm_system_raw_schema_check.md",
        processed_root / f"{run_id}_alarm_system_stability_schema_check.md",
    ]
    for path in [args.group_summary, llm_path, alarm_path, stability_path, *schema_paths]:
        require(path.is_file(), f"missing evidence: {path}")

    llm_rows = read_jsonl(llm_path)
    require(len(llm_rows) == 3, "text guard LLM row count")
    require(all(row.get("status") == "pass" for row in llm_rows), "text guard LLM pass status")
    require(all(not row.get("thinking_included") for row in llm_rows), "Qwen no-think output")
    pids = {row.get("resident_server_pid") for row in llm_rows}
    loads = {row.get("resident_model_load_count") for row in llm_rows}
    indexes = [row.get("resident_request_index") for row in llm_rows]
    require(len(pids) == 1 and None not in pids, "resident text pid reuse")
    require(loads == {1}, "resident text model-load reuse")
    require(indexes == sorted(indexes), "resident request ordering")

    alarms = read_jsonl(alarm_path)
    require(len(alarms) == 3, "text guard alarm row count")
    require(all(row.get("json_fact_conflict") is True for row in alarms), "fact conflicts recorded")
    require(
        all(row.get("fallback_status", {}).get("alarm_json") == "fact_conflict_detected" for row in alarms),
        "publishable fallback status",
    )
    require(all(row.get("fact_conflict_detail") for row in alarms), "fact conflict details")
    require(all(schema_pass(path) for path in schema_paths), "text guard schema checks")

    evidence_paths = [args.group_summary, code_boundary_path, *target_paths, llm_path, alarm_path, stability_path, *schema_paths]
    manifest = {
        "project": "05_alarm_system",
        "experiment_status": "closed",
        "acceptance_status": "dual_board_target_pass_publishable_text_guard_pass",
        "group_run_id": group["group_run_id"],
        "text_guard_run_id": run_id,
        "checks": {
            "dual_board_target_ready": True,
            "jetson_gate_pass": True,
            "rk3588_gate_pass": True,
            "overlap_gate_pass": True,
            "jetson_text_guard_llm_rows": len(llm_rows),
            "jetson_text_guard_alarm_rows": len(alarms),
            "jetson_text_guard_conflict_replacements": sum(bool(row.get("json_fact_conflict")) for row in alarms),
            "jetson_text_guard_schema_checks": len(schema_paths),
            "dual_board_target_schema_checks": sum(
                len(evidence["schema_checks"]) for evidence in target_evidence.values()
            ),
            "independent_runtime_pass": True,
        },
        "dual_board_metrics": {
            "start_skew_sec": group["start_skew_sec"],
            "window_overlap_sec": group["window_overlap_sec"],
            "required_overlap_sec": group["required_overlap_sec"],
            "jetson": group["jetson"],
            "rk3588": group["rk3588"],
        },
        "text_guard_metrics": {
            "resident_server_pid": next(iter(pids)),
            "resident_model_load_count": 1,
            "resident_request_indexes": indexes,
            "total_ms": [row.get("total_ms") for row in llm_rows],
            "decode_tokens_per_s": [row.get("decode_tokens_per_s") for row in llm_rows],
            "raw_llm_fact_conflict_count": len(alarms),
            "publishable_replacement_count": len(alarms),
        },
        "evidence": [
            {"path": relative_path(path), "sha256": sha256(path)}
            for path in evidence_paths
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Project 05 Final Acceptance Manifest",
        "",
        f"- acceptance_status: `{manifest['acceptance_status']}`",
        f"- group_run_id: `{manifest['group_run_id']}`",
        f"- text_guard_run_id: `{manifest['text_guard_run_id']}`",
        f"- dual_board_overlap_sec: `{group['window_overlap_sec']}`",
        f"- text_guard_replacements: `{len(alarms)}/{len(alarms)}`",
        "",
        "## Evidence Hashes",
        "",
        "| path | sha256 |",
        "|---|---|",
    ]
    lines.extend(f"| `{row['path']}` | `{row['sha256']}` |" for row in manifest["evidence"])
    args.output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"acceptance_status={manifest['acceptance_status']}")
    print(f"output_json={args.output_json}")
    print(f"output_md={args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
