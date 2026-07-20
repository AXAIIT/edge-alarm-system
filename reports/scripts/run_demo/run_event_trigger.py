#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import (
    COCO_CLASS_NAMES,
    clamp_box,
    detection_to_event_detection,
    parse_scalar,
    read_jsonl,
    utc_now_iso,
    write_jsonl,
)


def load_rule_config(path: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = {"defaults": {}, "rules": []}
    section = ""
    current_rule: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if indent == 0 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            cfg[key.strip()] = parse_scalar(raw_value.strip())
            continue
        if section == "defaults" and indent >= 2 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            cfg["defaults"][key.strip()] = parse_scalar(raw_value.strip())
            continue
        if section == "rules" and stripped.startswith("- "):
            current_rule = {}
            cfg["rules"].append(current_rule)
            item = stripped[2:].strip()
            if ":" in item:
                key, raw_value = item.split(":", 1)
                current_rule[key.strip()] = parse_scalar(raw_value.strip())
            continue
        if section == "rules" and current_rule is not None and indent >= 4 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            current_rule[key.strip()] = parse_scalar(raw_value.strip())
    defaults = cfg.get("defaults", {}) if isinstance(cfg.get("defaults"), dict) else {}
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules"), list) else []
    normalized_rules = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("enabled") is False:
            continue
        normalized_rules.append(
            {
                "rule_id": rule.get("rule_id", "generic_object_event"),
                "alarm_domain": rule.get("alarm_domain", defaults.get("alarm_domain", "visual_detection")),
                "alarm_type": rule.get("alarm_type") or rule.get("rule_id", "generic_object_event"),
                "class_filter": rule.get("class_filter") or [],
                "confidence_threshold": float(
                    rule.get("confidence_threshold", defaults.get("confidence_threshold", 0.5))
                ),
                "duration_frames": int(rule.get("duration_frames", defaults.get("duration_frames", 1))),
                "cooldown_seconds": float(rule.get("cooldown_seconds", defaults.get("cooldown_seconds", 0))),
                "min_object_count": int(rule.get("min_object_count", 1)),
                "zone": rule.get("zone"),
                "snapshot_policy": rule.get("snapshot_policy", "best_confidence"),
                "clip_policy": rule.get("clip_policy", "pre_post"),
                "priority": rule.get("priority", defaults.get("priority", "normal")),
            }
        )
    if not normalized_rules:
        normalized_rules.append(
            {
                "rule_id": "generic_object_event",
                "alarm_domain": defaults.get("alarm_domain", "visual_detection"),
                "alarm_type": "generic_object_event",
                "class_filter": [],
                "confidence_threshold": float(defaults.get("confidence_threshold", 0.5)),
                "duration_frames": int(defaults.get("duration_frames", 1)),
                "cooldown_seconds": float(defaults.get("cooldown_seconds", 0)),
                "min_object_count": 1,
                "zone": None,
                "snapshot_policy": "best_confidence",
                "clip_policy": "pre_post",
                "priority": defaults.get("priority", "normal"),
            }
        )
    return {
        "ruleset_id": cfg.get("ruleset_id", path.stem),
        "source_id": cfg.get("source_id") or "",
        "pre_event_seconds": defaults.get("pre_event_seconds", 1),
        "post_event_seconds": defaults.get("post_event_seconds", 2),
        "max_pending_events": int(defaults.get("max_pending_events", 16)),
        "rules": normalized_rules,
    }


def detection_class_name(det: dict[str, Any]) -> str:
    name = det.get("class_name")
    if isinstance(name, str) and name:
        return name
    try:
        return COCO_CLASS_NAMES.get(int(det.get("class_id")), str(det.get("class_id")))
    except (TypeError, ValueError):
        return str(det.get("class_id"))


def rule_matches_detection(det: dict[str, Any], rule: dict[str, Any]) -> bool:
    if float(det.get("confidence", 0.0)) < float(rule["confidence_threshold"]):
        return False
    class_filter = rule.get("class_filter") or []
    if not class_filter:
        return True
    class_name = detection_class_name(det)
    class_id = str(det.get("class_id"))
    allowed = {str(item) for item in class_filter}
    return class_name in allowed or class_id in allowed


def matching_detections(row: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    detections = row.get("detections") or []
    matched = [det for det in detections if rule_matches_detection(det, rule)]
    if len(matched) < int(rule.get("min_object_count", 1)):
        return []
    return matched


def build_event(
    row: dict[str, Any],
    run_id: str,
    sequence_index: int,
    ruleset: dict[str, Any],
    rule: dict[str, Any],
    raw_detections: list[dict[str, Any]],
) -> dict[str, Any]:
    frame_id = row.get("frame_id")
    width = row.get("input_width")
    height = row.get("input_height")
    threshold = rule["confidence_threshold"]
    detections = [
        detection_to_event_detection(det, idx, frame_id)
        for idx, det in enumerate(raw_detections)
    ]
    roi_boxes = []
    for det in detections:
        roi_boxes.append(
            {
                "detection_id": det["detection_id"],
                "bbox_xyxy": clamp_box(det["bbox"], width, height),
                "coordinate_space": "source_frame",
                "padding": 0.05,
                "resized_to": None,
            }
        )
    timestamp = row.get("timestamp") or row.get("capture_ts") or utc_now_iso()
    event_id = f"{run_id}_{rule['rule_id']}_{sequence_index:06d}_frame_{frame_id}"
    max_conf = max((d["confidence"] for d in detections), default=0.0)
    return {
        "event_id": event_id,
        "run_id": run_id,
        "board": row.get("board", "Jetson 8GB"),
        "target": row.get("target", "jetson_8gb"),
        "source_id": row.get("input_source_id") or ruleset.get("source_id") or "unknown_source",
        "camera_id": row.get("input_source_id") or "unknown_camera",
        "frame_id": frame_id,
        "timestamp": timestamp,
        "alarm_domain": rule.get("alarm_domain", "visual_detection"),
        "alarm_type": rule["alarm_type"],
        "event_stage": "candidate",
        "trigger_rule_id": rule["rule_id"],
        "trigger_reason": (
            f"alarm_domain={rule.get('alarm_domain', 'visual_detection')};"
            f"alarm_type={rule['alarm_type']};confidence>={threshold};"
            f"max_confidence={max_conf:.3f};detections={len(detections)};"
            f"duration_frames={rule['duration_frames']};cooldown_seconds={rule['cooldown_seconds']}"
        ),
        "detections": detections,
        "keyframe_path": None,
        "roi_paths": [],
        "roi_boxes": roi_boxes,
        "video_clip_path": None,
        "pre_event_seconds": ruleset["pre_event_seconds"],
        "post_event_seconds": ruleset["post_event_seconds"],
        "queue_depth_at_trigger": max(
            int(row.get("queue_capture_size") or 0),
            int(row.get("queue_preprocess_size") or 0),
            int(row.get("queue_infer_size") or 0),
            int(row.get("queue_postprocess_size") or 0),
        ),
        "detector_latency_ms": row.get("end_to_end_latency_ms"),
        "event_trigger_latency_ms": 0.0,
        "roi_crop_latency_ms": None,
        "video_clip_latency_ms": None,
        "queue_metrics": {
            "enqueue_ts": timestamp,
            "dequeue_ts": timestamp,
            "wait_ms": 0.0,
            "drop_policy": row.get("queue_policy") or "none",
            "drop_reason": row.get("dropped_frame_reason"),
            "priority": rule["priority"],
        },
        "status": "not_verified",
        "log_paths": {
            "runtime_log_path": row.get("runtime_log_path"),
            "failure_log_path": row.get("failure_log_path"),
            "detector_log_path": row.get("runtime_evidence_path") or row.get("runtime_log_path"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Project 05 event packages from detector JSONL.")
    parser.add_argument("--detections", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--min-frame-gap", type=int, default=30)
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()

    rows = read_jsonl(args.detections)
    ruleset = load_rule_config(args.rules)
    run_id = args.run_id or f"{rows[0].get('run_id', 'project3_inherited')}_p05_events"
    events: list[dict[str, Any]] = []
    last_frame_by_rule: dict[str, int] = {}
    consecutive_by_rule: dict[str, int] = {}
    for row in rows:
        frame_id = row.get("frame_id")
        try:
            frame_int = int(frame_id)
        except (TypeError, ValueError):
            frame_int = None
        for rule in ruleset["rules"]:
            rule_id = rule["rule_id"]
            matched = matching_detections(row, rule)
            if matched:
                consecutive_by_rule[rule_id] = consecutive_by_rule.get(rule_id, 0) + 1
            else:
                consecutive_by_rule[rule_id] = 0
                continue
            if consecutive_by_rule[rule_id] < int(rule["duration_frames"]):
                continue
            last_frame = last_frame_by_rule.get(rule_id)
            cooldown_frames = max(args.min_frame_gap, int(float(rule["cooldown_seconds"]) * args.fps))
            if last_frame is not None and frame_int is not None and frame_int - last_frame < cooldown_frames:
                continue
            events.append(build_event(row, run_id, len(events), ruleset, rule, matched))
            if frame_int is not None:
                last_frame_by_rule[rule_id] = frame_int
            if args.max_events and len(events) >= args.max_events:
                break
        if args.max_events and len(events) >= args.max_events:
            break
    count = write_jsonl(args.output, events)
    print(f"events_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
