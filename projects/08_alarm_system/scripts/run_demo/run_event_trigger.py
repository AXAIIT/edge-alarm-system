#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import (
    COCO_CLASS_NAMES,
    clamp_box,
    detection_to_event_detection,
    parse_scalar,
    read_jsonl,
    action_from_risk,
    risk_from_detections,
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
                "confirmation_window_seconds": float(
                    rule.get("confirmation_window_seconds", defaults.get("confirmation_window_seconds", 0.0))
                ),
                "keyframe_sample_count": int(
                    rule.get("keyframe_sample_count", defaults.get("keyframe_sample_count", 1))
                ),
                "min_positive_keyframes": int(
                    rule.get("min_positive_keyframes", defaults.get("min_positive_keyframes", 1))
                ),
                "cooldown_seconds": float(rule.get("cooldown_seconds", defaults.get("cooldown_seconds", 0))),
                "clear_after_frames": int(rule.get("clear_after_frames", defaults.get("clear_after_frames", 1))),
                "min_object_count": int(rule.get("min_object_count", 1)),
                "zone": rule.get("zone"),
                "snapshot_policy": rule.get("snapshot_policy", "best_confidence"),
                "clip_policy": rule.get("clip_policy", "pre_post"),
                "priority": rule.get("priority", defaults.get("priority", "normal")),
                "vlm_input_mode": rule.get(
                    "vlm_input_mode",
                    "relation_context_crop" if rule.get("alarm_type") == "multi_object_scene" else "object_roi",
                ),
                "context_padding_ratio": float(
                    rule.get("context_padding_ratio", defaults.get("context_padding_ratio", 0.25))
                ),
                "route_target": rule.get("route_target", defaults.get("route_target", "rule_only")),
                "route_reason": rule.get("route_reason", "rule_defined_route"),
                "text_purpose": rule.get("text_purpose"),
                "vlm_purpose": rule.get("vlm_purpose"),
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
                "confirmation_window_seconds": float(defaults.get("confirmation_window_seconds", 0.0)),
                "keyframe_sample_count": int(defaults.get("keyframe_sample_count", 1)),
                "min_positive_keyframes": int(defaults.get("min_positive_keyframes", 1)),
                "cooldown_seconds": float(defaults.get("cooldown_seconds", 0)),
                "clear_after_frames": int(defaults.get("clear_after_frames", 1)),
                "min_object_count": 1,
                "zone": None,
                "snapshot_policy": "best_confidence",
                "clip_policy": "pre_post",
                "priority": defaults.get("priority", "normal"),
                "vlm_input_mode": "object_roi",
                "context_padding_ratio": float(defaults.get("context_padding_ratio", 0.25)),
                "route_target": "rule_only",
                "route_reason": "generic_rule_defaults_to_rule_only",
                "text_purpose": None,
                "vlm_purpose": None,
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
    evidence_observations: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] | None = None,
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
    risk = risk_from_detections(detections)
    observations = evidence_observations or []
    evidence_frame_ids = [item[0] for item in observations]
    evidence_timestamps = [
        item[1].get("timestamp") or item[1].get("capture_ts")
        for item in observations
    ]
    route_target = str(rule.get("route_target") or "rule_only")
    evidence_hash_payload = {
        "rule_id": rule["rule_id"],
        "frame_ids": evidence_frame_ids,
        "detections": detections,
    }
    evidence_hash = hashlib.sha256(
        json.dumps(evidence_hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
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
        "alarm_revision": 0,
        "trigger_rule_id": rule["rule_id"],
        "risk_level": risk,
        "risk_basis": "legacy_common_risk_mapping",
        "allowed_actions": [action_from_risk(risk)],
        "trigger_reason": (
            f"alarm_domain={rule.get('alarm_domain', 'visual_detection')};"
            f"alarm_type={rule['alarm_type']};confidence>={threshold};"
            f"max_confidence={max_conf:.3f};detections={len(detections)};"
            f"confirmation_window_seconds={rule['confirmation_window_seconds']};"
            f"keyframe_sample_count={rule['keyframe_sample_count']};"
            f"cooldown_seconds={rule['cooldown_seconds']}"
        ),
        "detections": detections,
        "keyframe_path": None,
        "keyframe_paths": [],
        "roi_paths": [],
        "roi_boxes": roi_boxes,
        "context_crop_path": None,
        "context_crop_box": None,
        "context_detection_ids": [det["detection_id"] for det in detections],
        "context_padding_ratio": rule["context_padding_ratio"],
        "temporal_contact_sheet_path": None,
        "vlm_input_mode": rule["vlm_input_mode"],
        "evidence_frame_ids": evidence_frame_ids,
        "evidence_timestamps": evidence_timestamps,
        "confirmation_window_seconds": rule["confirmation_window_seconds"],
        "keyframe_sample_count": rule["keyframe_sample_count"],
        "min_positive_keyframes": rule["min_positive_keyframes"],
        "route_target": route_target,
        "route_reason": rule.get("route_reason") or "rule_defined_route",
        "needs_text": route_target in {"text_only", "text_then_vlm", "vlm_then_text"},
        "needs_vlm": route_target in {"vlm_only", "text_then_vlm", "vlm_then_text"},
        "text_purpose": rule.get("text_purpose"),
        "vlm_purpose": rule.get("vlm_purpose"),
        "evidence_hash": evidence_hash,
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


@dataclass
class RuleRuntimeState:
    observations: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = field(default_factory=list)
    active: bool = False
    clear_frames: int = 0
    last_seen_frame: int | None = None
    last_processed_frame: int | None = None
    cooldown_until_frame: int | None = None


def sample_observations(
    observations: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
    count: int,
) -> list[tuple[int, dict[str, Any], list[dict[str, Any]]]]:
    if not observations:
        return []
    count = max(1, min(int(count), len(observations)))
    if count == 1:
        return [observations[-1]]
    indexes = [round(index * (len(observations) - 1) / (count - 1)) for index in range(count)]
    return [observations[index] for index in indexes]


class EventRuleStateMachine:
    """Scene-level event state used when tracking IDs are unavailable.

    A rule must remain positive for its confirmation window. One event is emitted, then the
    state remains active until enough negative frames close it. Cooldown starts from the last
    positive observation, so a continuously visible object cannot retrigger periodically.
    """

    def __init__(self, ruleset: dict[str, Any], run_id: str, fps: float) -> None:
        self.ruleset = ruleset
        self.run_id = run_id
        self.fps = max(0.001, float(fps))
        self.states = {rule["rule_id"]: RuleRuntimeState() for rule in ruleset["rules"]}
        self.cooldown_suppressed = 0
        self.active_merged = 0

    def process(self, row: dict[str, Any], sequence_start: int) -> list[dict[str, Any]]:
        try:
            frame_id = int(row.get("frame_id"))
        except (TypeError, ValueError):
            return []
        events: list[dict[str, Any]] = []
        for rule in self.ruleset["rules"]:
            state = self.states[rule["rule_id"]]
            previous_processed_frame = state.last_processed_frame
            state.last_processed_frame = frame_id
            if previous_processed_frame is not None and frame_id != previous_processed_frame + 1:
                state.observations.clear()
                if state.active and frame_id > previous_processed_frame + 1:
                    state.clear_frames += frame_id - previous_processed_frame - 1
                    if state.clear_frames >= max(1, int(rule["clear_after_frames"])):
                        state.active = False
                        cooldown_frames = math.ceil(float(rule["cooldown_seconds"]) * self.fps)
                        last_seen = state.last_seen_frame if state.last_seen_frame is not None else previous_processed_frame
                        state.cooldown_until_frame = last_seen + cooldown_frames
            matched = matching_detections(row, rule)
            if not matched:
                state.observations.clear()
                if state.active:
                    state.clear_frames += 1
                    if state.clear_frames >= max(1, int(rule["clear_after_frames"])):
                        state.active = False
                        cooldown_frames = math.ceil(float(rule["cooldown_seconds"]) * self.fps)
                        last_seen = state.last_seen_frame if state.last_seen_frame is not None else frame_id
                        state.cooldown_until_frame = last_seen + cooldown_frames
                continue

            state.last_seen_frame = frame_id
            state.clear_frames = 0
            if state.active:
                self.active_merged += 1
                continue
            if state.cooldown_until_frame is not None and frame_id < state.cooldown_until_frame:
                self.cooldown_suppressed += 1
                continue

            state.observations.append((frame_id, row, matched))
            confirmation_frames = max(
                int(rule["duration_frames"]),
                math.ceil(float(rule["confirmation_window_seconds"]) * self.fps),
            )
            span_frames = state.observations[-1][0] - state.observations[0][0] + 1
            if span_frames < confirmation_frames:
                continue
            sampled = sample_observations(state.observations, int(rule["keyframe_sample_count"]))
            if len(sampled) < int(rule["min_positive_keyframes"]):
                continue
            event = build_event(
                row,
                self.run_id,
                sequence_start + len(events),
                self.ruleset,
                rule,
                matched,
                sampled,
            )
            state.active = True
            state.observations.clear()
            events.append(event)
        return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Project 08 event packages from detector JSONL.")
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
    run_id = args.run_id or f"{rows[0].get('run_id', 'project3_inherited')}_p08_events"
    events: list[dict[str, Any]] = []
    state_machine = EventRuleStateMachine(ruleset, run_id, args.fps)
    for row in rows:
        for event in state_machine.process(row, len(events)):
            events.append(event)
            if args.max_events and len(events) >= args.max_events:
                break
        if args.max_events and len(events) >= args.max_events:
            break
    count = write_jsonl(args.output, events)
    print(f"events_written={count}")
    print(f"active_merged={state_machine.active_merged}")
    print(f"cooldown_suppressed={state_machine.cooldown_suppressed}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
