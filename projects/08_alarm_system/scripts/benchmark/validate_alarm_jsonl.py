#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc


def check_required(row: dict[str, Any], required: list[str], prefix: str, errors: list[str]) -> None:
    for key in required:
        if key not in row:
            errors.append(f"{prefix}: missing required field {key}")


def check_schema_specific(row: dict[str, Any], schema_id: str, prefix: str, errors: list[str]) -> None:
    if schema_id == "alarm_system_raw_schema.json":
        if row.get("project") != "08_alarm_system":
            errors.append(f"{prefix}: project must be 08_alarm_system")
        if row.get("measurement_granularity") != "per_event":
            errors.append(f"{prefix}: measurement_granularity must be per_event")
        if not isinstance(row.get("json_schema_pass"), bool):
            errors.append(f"{prefix}: json_schema_pass must be boolean")
        fallback = row.get("fallback_status")
        if not isinstance(fallback, dict):
            errors.append(f"{prefix}: fallback_status must be object")
        else:
            check_required(fallback, ["detector", "event_trigger", "vlm", "video", "llm", "alarm_json"], prefix, errors)
    elif schema_id == "alarm_event_package_schema.json":
        if row.get("target") not in {"jetson_8gb", "rk3588_8gb", "pc"}:
            errors.append(f"{prefix}: invalid target")
        if not isinstance(row.get("detections"), list):
            errors.append(f"{prefix}: detections must be array")
        for i, det in enumerate(row.get("detections") or []):
            check_required(det, ["detection_id", "class_id", "confidence", "bbox"], f"{prefix}.detections[{i}]", errors)
        queue = row.get("queue_metrics")
        if not isinstance(queue, dict):
            errors.append(f"{prefix}: queue_metrics must be object")
        else:
            check_required(queue, ["enqueue_ts", "dequeue_ts", "wait_ms", "drop_policy", "drop_reason", "priority"], prefix, errors)
        route_target = row.get("route_target")
        expected_flags = {
            "rule_only": (False, False),
            "template_only": (False, False),
            "text_only": (True, False),
            "vlm_only": (False, True),
            "vlm_then_text": (True, True),
            "text_then_vlm": (True, True),
        }
        if route_target not in expected_flags:
            errors.append(f"{prefix}: invalid route_target {route_target}")
        else:
            expected_text, expected_vlm = expected_flags[route_target]
            if row.get("needs_text") is not expected_text:
                errors.append(f"{prefix}: needs_text does not match route_target {route_target}")
            if row.get("needs_vlm") is not expected_vlm:
                errors.append(f"{prefix}: needs_vlm does not match route_target {route_target}")
        alarm_type = row.get("alarm_type")
        if alarm_type in {"person_presence", "vehicle_presence"} and route_target != "rule_only":
            errors.append(f"{prefix}: {alarm_type} must use rule_only")
        if alarm_type == "multi_object_scene":
            if route_target not in {"text_then_vlm", "vlm_then_text"}:
                errors.append(f"{prefix}: multi_object_scene must use text_then_vlm or vlm_then_text")
            if len(row.get("detections") or []) < 2:
                errors.append(f"{prefix}: multi_object_scene requires at least two detections")
        evidence_hash = row.get("evidence_hash")
        if not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
            errors.append(f"{prefix}: evidence_hash must be a 64-character SHA-256 hex string")
    elif schema_id == "alarm_event_schema.json":
        if row.get("project") == "08_alarm_system":
            errors.append(f"{prefix}: final alarm JSON should not contain project field")
        if not isinstance(row.get("json_fact_conflict"), bool):
            errors.append(f"{prefix}: json_fact_conflict must be boolean")
        for i, det in enumerate(row.get("detections") or []):
            check_required(det, ["detection_id", "class_id", "confidence", "bbox", "source"], f"{prefix}.detections[{i}]", errors)
            if det.get("source") != "event_package":
                errors.append(f"{prefix}.detections[{i}]: source must be event_package")
        fallback = row.get("fallback_status")
        if not isinstance(fallback, dict):
            errors.append(f"{prefix}: fallback_status must be object")
        else:
            check_required(fallback, ["detector", "event_trigger", "vlm", "video", "llm", "alarm_json"], prefix, errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Project 08 JSONL schema checker.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    schema = load_schema(args.schema)
    schema_id = schema.get("$id") or args.schema.name
    required = schema.get("required", [])
    rows = 0
    errors: list[str] = []
    for line_no, row in iter_jsonl(args.input):
        rows += 1
        if not isinstance(row, dict):
            errors.append(f"line {line_no}: row must be object")
            continue
        prefix = f"line {line_no}"
        check_required(row, required, prefix, errors)
        check_schema_specific(row, schema_id, prefix, errors)
    if rows == 0:
        errors.append("input has no JSONL rows")

    status = "fail" if errors else "pass"
    lines = [
        "# Project 08 schema check",
        "",
        f"- input: `{args.input}`",
        f"- schema: `{args.schema}`",
        f"- schema_id: `{schema_id}`",
        f"- rows: {rows}",
        f"- status: {status}",
    ]
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {err}" for err in errors)
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
