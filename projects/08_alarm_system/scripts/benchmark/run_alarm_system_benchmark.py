#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import index_by_event_id, parse_simple_yaml, read_jsonl, utc_now_iso, write_jsonl


def max_or_none(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return max(nums) if nums else None


def build_raw_row(
    event: dict[str, Any],
    alarm: dict[str, Any] | None,
    combo: dict[str, Any],
    board: str,
    environment_baseline_id: str,
    events_path: Path,
    alarms_path: Path,
    run_id_override: str | None = None,
) -> dict[str, Any]:
    detector = combo.get("detector", {})
    text_llm = combo.get("text_llm", {})
    image_vlm = combo.get("image_vlm", {})
    video_vlm = combo.get("video_vlm", {})
    fallback = alarm.get("fallback_status") if alarm else None
    metrics = alarm.get("system_metrics") if alarm else {}
    if not isinstance(metrics, dict):
        metrics = {}
    detections = event.get("detections") or []
    end_to_end = max_or_none(
        [
            event.get("detector_latency_ms"),
            event.get("event_trigger_latency_ms"),
            event.get("roi_crop_latency_ms"),
            event.get("video_clip_latency_ms"),
            metrics.get("llm_total_ms"),
            metrics.get("vlm_total_ms"),
            metrics.get("video_understanding_total_ms"),
        ]
    )
    return {
        "run_id": run_id_override or event.get("run_id", "unknown_run"),
        "timestamp": alarm.get("timestamp") if alarm else event.get("timestamp") or utc_now_iso(),
        "schema_version": 1,
        "project": "08_alarm_system",
        "measurement_granularity": "per_event",
        "board": event.get("board", board),
        "target": event.get("target", board),
        "environment_baseline_id": environment_baseline_id,
        "event_id": event.get("event_id"),
        "alarm_domain": (alarm or event).get("alarm_domain", "visual_detection"),
        "alarm_type": (alarm or event).get("alarm_type", "generic_object_event"),
        "event_stage": (alarm or event).get("event_stage", event.get("event_stage", "candidate")),
        "route_target": event.get("route_target", "rule_only"),
        "route_reason": event.get("route_reason"),
        "needs_text": bool(event.get("needs_text")),
        "needs_vlm": bool(event.get("needs_vlm")),
        "text_purpose": event.get("text_purpose"),
        "vlm_purpose": event.get("vlm_purpose"),
        "evidence_hash": event.get("evidence_hash"),
        "route_decision": event.get("route_decision") or {},
        "input_source_id": event.get("source_id"),
        "frame_id": event.get("frame_id"),
        "model_combo_id": combo.get("model_combo_id", "unknown_combo"),
        "detector_backend": detector.get("backend"),
        "detector_artifact_sha256": detector.get("artifact_sha256"),
        "detector_precision": detector.get("precision"),
        "llm_model": text_llm.get("model"),
        "vlm_model": image_vlm.get("model") if image_vlm.get("enabled") is not False else None,
        "video_model": video_vlm.get("model") if video_vlm.get("enabled") is not False else None,
        "project08_model_refs": [combo.get("model_spec_ref", "projects/08_alarm_system/README.md")],
        "detection_latency_ms": event.get("detector_latency_ms"),
        "event_trigger_latency_ms": event.get("event_trigger_latency_ms"),
        "roi_crop_latency_ms": event.get("roi_crop_latency_ms"),
        "video_clip_latency_ms": event.get("video_clip_latency_ms"),
        "vlm_total_ms": metrics.get("vlm_total_ms"),
        "video_understanding_total_ms": metrics.get("video_understanding_total_ms"),
        "llm_first_token_ms": metrics.get("llm_first_token_ms"),
        "llm_decode_tokens_per_s": metrics.get("llm_decode_tokens_per_s"),
        "llm_total_ms": metrics.get("llm_total_ms"),
        "json_schema_pass": alarm is not None,
        "json_fact_conflict": bool(alarm.get("json_fact_conflict")) if alarm else False,
        "json_repair_count": 0,
        "end_to_end_alarm_ms": end_to_end,
        "memory_peak_mb": None,
        "swap_used_mb": None,
        "temperature_max_c": None,
        "power_w": None,
        "power_mode": None,
        "cpu_gpu_npu_bpu_utilization": {
            "cpu_peak": None,
            "gpu_peak": None,
            "npu_peak": None,
            "bpu_peak": None,
            "unavailable_metrics": ["project08_dryrun_no_monitor"],
        },
        "queue_depth_max": event.get("queue_depth_at_trigger"),
        "drop_count": 0,
        "fallback_status": fallback
        or {
            "detector": "ok" if detections else "not_executed",
            "event_trigger": "ok",
            "vlm": "not_executed",
            "video": "disabled_by_project08_scope",
            "llm": "not_executed",
            "alarm_json": "not_executed",
        },
        "status": "not_verified" if event.get("status") == "not_verified" else "pass",
        "raw_event_path": str(events_path),
        "alarm_json_path": str(alarms_path) if alarm else None,
        "runtime_log_path": event.get("log_paths", {}).get("runtime_log_path"),
        "monitor_log_path": None,
        "failure_log_path": event.get("log_paths", {}).get("failure_log_path"),
        "related_troubleshooting_id": "P08-CONCURRENCY-PENDING-001"
        if event.get("target") == "jetson_8gb"
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Project 08 per-event benchmark raw JSONL.")
    parser.add_argument("--board", default="jetson_8gb")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--alarms", required=True, type=Path)
    parser.add_argument("--model-config", type=Path, default=Path("projects/08_alarm_system/configs/models/jetson_model_combo.yaml"))
    parser.add_argument("--environment-baseline-id", default="20260609_jetson_8gb_env_baseline")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    events = read_jsonl(args.events)
    alarms_by_event = index_by_event_id(read_jsonl(args.alarms))
    combo = parse_simple_yaml(args.model_config)
    rows = [
        build_raw_row(
            event,
            alarms_by_event.get(event.get("event_id")),
            combo,
            args.board,
            args.environment_baseline_id,
            args.events,
            args.alarms,
        )
        for event in events
    ]
    count = write_jsonl(args.output, rows)
    print(f"benchmark_rows_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
