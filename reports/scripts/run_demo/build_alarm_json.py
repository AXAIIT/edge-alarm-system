#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    action_from_risk,
    index_by_event_id,
    parse_simple_yaml,
    read_jsonl,
    risk_from_detections,
    utc_now_iso,
    write_jsonl,
)


def optional_rows(path_arg: str | None) -> list[dict[str, Any]]:
    if not path_arg or path_arg == "none":
        return []
    path = Path(path_arg)
    if not path.exists():
        return []
    return read_jsonl(path)


def text_from_model(row: dict[str, Any] | None, keys: list[str]) -> str | None:
    if not row:
        return None
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def status_from_model(row: dict[str, Any] | None, ok_statuses: set[str]) -> str:
    if not row:
        return "not_executed"
    status = row.get("status")
    if status in ok_statuses:
        return "ok"
    if status == "timeout":
        return "timeout"
    if status in {"stub", "template_fallback"}:
        return "template_fallback"
    if status == "not_executed":
        return "not_executed"
    return "failed"


def metric(row: dict[str, Any] | None, key: str) -> Any:
    return row.get(key) if row else None


def model_versions(combo: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_combo_id": combo.get("model_combo_id"),
        "detector": combo.get("detector", {}),
        "text_llm": combo.get("text_llm", {}),
        "image_vlm": combo.get("image_vlm", {}),
        "video_vlm": combo.get("video_vlm", {}),
    }


def build_alarm(
    event: dict[str, Any],
    combo: dict[str, Any],
    llm_by_event: dict[str, dict[str, Any]],
    vlm_by_event: dict[str, dict[str, Any]],
    video_by_event: dict[str, dict[str, Any]],
    raw_result_path: str | None,
) -> dict[str, Any]:
    event_id = event["event_id"]
    llm_row = llm_by_event.get(event_id)
    vlm_row = vlm_by_event.get(event_id)
    video_row = video_by_event.get(event_id)
    detections = []
    for det in event.get("detections", []):
        copied = dict(det)
        copied["source"] = "event_package"
        detections.append(copied)
    risk = risk_from_detections(detections)
    llm_text = text_from_model(llm_row, ["llm_explanation", "text", "output", "summary"])
    if llm_text is None:
        llm_text = f"Template fallback: detected {len(detections)} object(s); keep detector facts unchanged."
    vlm_text = text_from_model(vlm_row, ["vlm_summary", "text", "output", "summary"])
    video_text = text_from_model(video_row, ["video_summary", "text", "output", "summary"])
    if video_text is None and combo.get("video_vlm", {}).get("project4_admission_level") == "D_not_used":
        video_text = "Video model disabled by Project 04 decision; summary is derived from detector/event facts only."
    llm_status = status_from_model(llm_row, {"pass", "ok"})
    vlm_status = status_from_model(vlm_row, {"pass", "ok"})

    return {
        "event_id": event_id,
        "timestamp": event.get("timestamp") or utc_now_iso(),
        "schema_version": 1,
        "board": event.get("board", "Jetson 8GB"),
        "target": event.get("target", "jetson_8gb"),
        "alarm_domain": event.get("alarm_domain", "visual_detection"),
        "alarm_type": event.get("alarm_type", "generic_object_event"),
        "event_stage": event.get("event_stage", "candidate"),
        "camera_id": event.get("camera_id") or event.get("source_id") or "unknown_camera",
        "source_frame": {
            "frame_id": event.get("frame_id"),
            "timestamp": event.get("timestamp") or utc_now_iso(),
            "path": event.get("keyframe_path"),
        },
        "detections": detections,
        "roi_paths": event.get("roi_paths") or [],
        "video_clip_path": event.get("video_clip_path"),
        "vlm_summary": vlm_text,
        "video_summary": video_text,
        "llm_explanation": llm_text,
        "risk_level": risk,
        "recommended_action": action_from_risk(risk),
        "system_metrics": {
            "detector_latency_ms": event.get("detector_latency_ms"),
            "event_trigger_latency_ms": event.get("event_trigger_latency_ms"),
            "roi_crop_latency_ms": event.get("roi_crop_latency_ms"),
            "video_clip_latency_ms": event.get("video_clip_latency_ms"),
            "queue_depth_at_trigger": event.get("queue_depth_at_trigger"),
            "llm_first_token_ms": metric(llm_row, "first_token_ms"),
            "llm_prefill_ms": metric(llm_row, "prefill_ms"),
            "llm_decode_tokens_per_s": metric(llm_row, "decode_tokens_per_s"),
            "llm_total_ms": metric(llm_row, "total_ms"),
            "llm_prompt_tokens": metric(llm_row, "prompt_tokens"),
            "llm_output_tokens": metric(llm_row, "output_tokens"),
            "vlm_image_preprocess_ms": metric(vlm_row, "image_preprocess_ms"),
            "vlm_total_ms": metric(vlm_row, "vlm_total_ms"),
            "video_understanding_total_ms": metric(video_row, "video_total_ms")
            or metric(video_row, "video_understanding_total_ms")
            or metric(video_row, "total_ms"),
        },
        "model_versions": model_versions(combo),
        "project4_decision_refs": [
            "projects/04_llm_vlm_independent/reports/project5_integration_decision.md",
            "projects/04_llm_vlm_independent/reports/llm_vlm_model_matrix.md",
        ],
        "fallback_status": {
            "detector": "ok",
            "event_trigger": "ok",
            "vlm": vlm_status if vlm_status != "template_fallback" else "not_executed",
            "video": "disabled_by_project4_decision"
            if combo.get("video_vlm", {}).get("project4_admission_level") == "D_not_used"
            else ("ok" if video_row else "not_executed"),
            "llm": llm_status if llm_row else "template_fallback",
            "alarm_json": "ok",
        },
        "evidence": {
            "event_package_path": None,
            "raw_result_path": raw_result_path,
            "runtime_log_path": event.get("log_paths", {}).get("runtime_log_path"),
            "monitor_log_path": None,
            "failure_log_path": event.get("log_paths", {}).get("failure_log_path"),
            "project4_decision_report": "projects/04_llm_vlm_independent/reports/project5_integration_decision.md",
        },
        "json_fact_conflict": False,
        "fact_conflict_detail": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Project 05 structured alarm JSONL.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--llm", default="none")
    parser.add_argument("--vlm", default="none")
    parser.add_argument("--video", default="none")
    parser.add_argument("--schema", type=Path, default=Path("projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json"))
    parser.add_argument("--model-config", type=Path, default=Path("projects/05_alarm_system/configs/models/jetson_model_combo.yaml"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    combo = parse_simple_yaml(args.model_config)
    events = read_jsonl(args.events)
    llm_by_event = index_by_event_id(optional_rows(args.llm))
    vlm_by_event = index_by_event_id(optional_rows(args.vlm))
    video_by_event = index_by_event_id(optional_rows(args.video))
    alarms = [build_alarm(event, combo, llm_by_event, vlm_by_event, video_by_event, str(args.output)) for event in events]
    for alarm in alarms:
        alarm["evidence"]["event_package_path"] = str(args.events)
    count = write_jsonl(args.output, alarms)
    print(f"alarms_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
