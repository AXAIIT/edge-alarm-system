#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from common import clamp_box, read_jsonl, write_jsonl

SERVICE_DIR = Path(__file__).resolve().parents[1] / "service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from asset_worker import (  # noqa: E402
    evidence_frame_ids,
    expand_box,
    write_relation_context_crop,
    write_temporal_contact_sheet,
)


def require_cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise SystemExit("OpenCV python package is required: install python3-opencv or run inside the Project3 runtime env") from exc
    return cv2


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)[:160] or "event"


def get_event_boxes(event: dict[str, Any]) -> list[dict[str, Any]]:
    roi_boxes = event.get("roi_boxes") or []
    if roi_boxes:
        return [box for box in roi_boxes if isinstance(box, dict)]
    result = []
    for det in event.get("detections") or []:
        bbox = det.get("bbox")
        if bbox:
            result.append({"bbox_xyxy": bbox, "detection_id": det.get("detection_id"), "class_name": det.get("class_name")})
    return result


def read_frame(cap: Any, frame_id: int):
    cv2 = require_cv2()
    if frame_id < 0:
        frame_id = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
    ok, frame = cap.read()
    if ok:
        return frame
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Project 08 multi-keyframe, ROI, relation-context, and temporal assets from a saved detector video."
    )
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path, help="Saved Project3 output video. Use SAVE_OUTPUT_VIDEO=1 in Project3.")
    parser.add_argument("--asset-dir", required=True, type=Path)
    parser.add_argument("--output-events", required=True, type=Path)
    parser.add_argument("--image-ext", choices=["jpg", "png"], default="jpg")
    parser.add_argument("--jpeg-quality", type=int, default=92)
    parser.add_argument("--max-events", type=int, default=0)
    args = parser.parse_args()

    cv2 = require_cv2()
    if not args.video.exists():
        raise SystemExit(f"--video not found: {args.video}")
    events = read_jsonl(args.events)
    if args.max_events:
        events = events[: args.max_events]

    args.asset_dir.mkdir(parents=True, exist_ok=True)
    keyframe_dir = args.asset_dir / "keyframes"
    roi_dir = args.asset_dir / "rois"
    context_dir = args.asset_dir / "context"
    keyframe_dir.mkdir(parents=True, exist_ok=True)
    roi_dir.mkdir(parents=True, exist_ok=True)
    context_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"failed to open video: {args.video}")

    encode_params = []
    if args.image_ext == "jpg":
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, args.jpeg_quality))]

    updated = []
    extracted_events = 0
    extracted_rois = 0
    extracted_context_crops = 0
    extracted_temporal_sheets = 0
    failures = 0
    started = time.monotonic()

    try:
        for event in events:
            row = dict(event)
            frame_id_raw = row.get("frame_id")
            try:
                frame_id = int(frame_id_raw)
            except (TypeError, ValueError):
                row["status"] = "degraded"
                row.setdefault("asset_generation_error", "invalid_frame_id")
                failures += 1
                updated.append(row)
                continue

            frame = read_frame(cap, frame_id)
            if frame is None:
                row["status"] = "degraded"
                row.setdefault("asset_generation_error", "frame_read_failed")
                failures += 1
                updated.append(row)
                continue

            height, width = frame.shape[:2]
            event_name = safe_name(str(row.get("event_id") or f"frame_{frame_id}"))
            keyframe_paths: list[str] = []
            evidence_frames: list[tuple[int, Any]] = []
            keyframe_path: Path | None = None
            for evidence_frame_id in evidence_frame_ids(row, frame_id):
                evidence_frame = frame if evidence_frame_id == frame_id else read_frame(cap, evidence_frame_id)
                if evidence_frame is None:
                    continue
                written = keyframe_dir / f"{event_name}_frame_{evidence_frame_id}.{args.image_ext}"
                if not cv2.imwrite(str(written), evidence_frame, encode_params):
                    continue
                keyframe_paths.append(str(written))
                evidence_frames.append((evidence_frame_id, evidence_frame))
                if evidence_frame_id == frame_id:
                    keyframe_path = written
            if keyframe_path is None:
                row["status"] = "degraded"
                row.setdefault("asset_generation_error", "keyframe_write_failed")
                failures += 1
                updated.append(row)
                continue

            roi_paths: list[str] = []
            roi_boxes_out = []
            for index, roi_box in enumerate(get_event_boxes(row)):
                bbox = roi_box.get("bbox_xyxy") or roi_box.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                x1, y1, x2, y2 = expand_box(
                    [float(v) for v in bbox[:4]],
                    width,
                    height,
                    float(roi_box.get("padding", 0.05) or 0.0),
                )
                ix1, iy1 = int(max(0, min(width - 1, round(x1)))), int(max(0, min(height - 1, round(y1))))
                ix2, iy2 = int(max(0, min(width, round(x2)))), int(max(0, min(height, round(y2))))
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                crop = frame[iy1:iy2, ix1:ix2]
                roi_path = roi_dir / f"{event_name}_roi_{index:02d}.{args.image_ext}"
                if not cv2.imwrite(str(roi_path), crop, encode_params):
                    continue
                roi_paths.append(str(roi_path))
                copied_box = dict(roi_box)
                copied_box["bbox_xyxy"] = [x1, y1, x2, y2]
                copied_box["roi_path"] = str(roi_path)
                roi_boxes_out.append(copied_box)

            context_path, context_box, context_detection_ids = write_relation_context_crop(
                cv2,
                frame,
                row,
                context_dir / f"{event_name}_context.{args.image_ext}",
                width,
                height,
                encode_params,
            )
            if context_path is not None:
                extracted_context_crops += 1
            temporal_contact_sheet_path = write_temporal_contact_sheet(
                cv2,
                evidence_frames,
                context_dir / f"{event_name}_temporal.{args.image_ext}",
                encode_params,
            )
            if temporal_contact_sheet_path is not None:
                extracted_temporal_sheets += 1

            row["keyframe_path"] = str(keyframe_path)
            row["keyframe_paths"] = keyframe_paths
            row["roi_paths"] = roi_paths
            row["roi_boxes"] = roi_boxes_out or row.get("roi_boxes") or []
            row["context_crop_path"] = str(context_path) if context_path is not None else None
            row["context_crop_box"] = context_box
            row["context_detection_ids"] = context_detection_ids
            row["temporal_contact_sheet_path"] = (
                str(temporal_contact_sheet_path) if temporal_contact_sheet_path is not None else None
            )
            row["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0 / max(1, len(updated) + 1), 3)
            row["video_clip_path"] = row.get("video_clip_path")
            row["asset_source_video_path"] = str(args.video)
            input_mode = str(row.get("vlm_input_mode") or "object_roi")
            asset_ready = bool(roi_paths)
            if input_mode == "relation_context_crop":
                asset_ready = context_path is not None or keyframe_path is not None
            elif input_mode in {"temporal_frames", "temporal_frames_required"}:
                asset_ready = temporal_contact_sheet_path is not None
            elif input_mode == "full_keyframe":
                asset_ready = keyframe_path is not None
            if asset_ready:
                if row.get("status") == "degraded":
                    row["status"] = "not_verified"
                extracted_events += 1
                extracted_rois += len(roi_paths)
            else:
                row["status"] = "degraded"
                row.setdefault("asset_generation_error", "no_valid_task_visual_asset")
                failures += 1
            updated.append(row)
    finally:
        cap.release()

    count = write_jsonl(args.output_events, updated)
    print(f"events_read={len(events)}")
    print(f"events_written={count}")
    print(f"events_with_visual_assets={extracted_events}")
    print(f"roi_images_written={extracted_rois}")
    print(f"context_crops_written={extracted_context_crops}")
    print(f"temporal_contact_sheets_written={extracted_temporal_sheets}")
    print(f"asset_failures={failures}")
    print(f"asset_dir={args.asset_dir}")
    print(f"output_events={args.output_events}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
