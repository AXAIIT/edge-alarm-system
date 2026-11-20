#!/usr/bin/env python3
"""Shared helpers for Project 08 alarm-system scripts.

The scripts in this project intentionally avoid third-party dependencies so they can run on
minimal board environments. They do not implement a full YAML or JSON Schema engine; they parse
the narrow project-owned config shapes needed for benchmark plumbing and perform explicit checks
for the required evidence fields.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


COCO_CLASS_NAMES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    4: "airplane",
    5: "bus",
    6: "train",
    7: "truck",
    8: "boat",
    9: "traffic light",
    10: "fire hydrant",
    11: "stop sign",
    12: "parking meter",
    13: "bench",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise SystemExit(f"{path}:{line_no}: expected object row")
            rows.append(obj)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def load_json_if_present(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the simple nested key/value YAML used by Project 08 configs.

    Supports two-space indentation, scalar values, and empty/null values. It is deliberately small
    and should not be used as a general YAML parser.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = parse_scalar(raw_value.strip())
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip() == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = value
    return root


def parse_scalar(value: str) -> Any:
    if value in {"", "null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def xywh_to_xyxy(bbox_xywh: list[float | int]) -> list[float]:
    x, y, w, h = [float(v) for v in bbox_xywh[:4]]
    return [x, y, x + w, y + h]


def clamp_box(box: list[float], width: int | None, height: int | None) -> list[float]:
    x1, y1, x2, y2 = box
    if width is not None:
        x1 = max(0.0, min(float(width), x1))
        x2 = max(0.0, min(float(width), x2))
    if height is not None:
        y1 = max(0.0, min(float(height), y1))
        y2 = max(0.0, min(float(height), y2))
    return [round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)]


def detection_to_event_detection(det: dict[str, Any], index: int, frame_id: Any) -> dict[str, Any]:
    class_id = det.get("class_id")
    bbox = det.get("bbox")
    if bbox is None and "bbox_xywh" in det:
        bbox = xywh_to_xyxy(det["bbox_xywh"])
    if bbox is None:
        bbox = [0.0, 0.0, 0.0, 0.0]
    try:
        class_name = COCO_CLASS_NAMES.get(int(class_id), None)
    except (TypeError, ValueError):
        class_name = None
    return {
        "detection_id": f"{frame_id}_{index}",
        "class_id": class_id,
        "class_name": class_name,
        "confidence": float(det.get("confidence", 0.0)),
        "bbox": [round(float(v), 3) for v in bbox[:4]],
    }


def risk_from_detections(detections: list[dict[str, Any]]) -> str:
    if not detections:
        return "info"
    max_conf = max(float(d.get("confidence", 0.0)) for d in detections)
    classes = {str(d.get("class_name") or d.get("class_id")) for d in detections}
    if max_conf >= 0.85 or {"person", "bus", "truck", "train"} & classes:
        return "high"
    if max_conf >= 0.65:
        return "medium"
    if max_conf >= 0.40:
        return "low"
    return "info"


def action_from_risk(risk: str) -> str:
    return {
        "critical": "escalate",
        "high": "notify_operator",
        "medium": "inspect_site",
        "low": "observe",
        "info": "observe",
    }.get(risk, "observe")


def index_by_event_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = row.get("event_id")
        if isinstance(event_id, str):
            result[event_id] = row
    return result
