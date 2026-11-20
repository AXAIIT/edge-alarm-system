#!/usr/bin/env python3
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sys

RUN_DEMO_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(RUN_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DEMO_DIR))

from common import clamp_box  # noqa: E402


def require_cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "OpenCV python package is required for Project 08 AssetWorker: "
            "install python3-opencv or run inside the Project 03/08 runtime environment"
        ) from exc
    return cv2


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)[:160] or "event"


def resolve_existing_path(raw: str, playlist_path: Path | None = None) -> Path:
    candidate = Path(raw)
    if candidate.exists():
        return candidate
    if playlist_path is not None:
        candidate = playlist_path.parent / raw
        if candidate.exists():
            return candidate
    raise SystemExit(f"asset source path not found: {raw}")


def get_event_boxes(event: dict[str, Any]) -> list[dict[str, Any]]:
    roi_boxes = event.get("roi_boxes") or []
    if roi_boxes:
        return [box for box in roi_boxes if isinstance(box, dict)]
    result = []
    for det in event.get("detections") or []:
        bbox = det.get("bbox")
        if bbox:
            result.append(
                {
                    "detection_id": det.get("detection_id"),
                    "bbox_xyxy": bbox,
                    "coordinate_space": "source_frame",
                    "padding": 0.05,
                    "resized_to": None,
                }
            )
    return result


def expand_box(
    bbox: list[float],
    width: int,
    height: int,
    padding_ratio: float,
) -> list[float]:
    x1, y1, x2, y2 = clamp_box([float(value) for value in bbox[:4]], width, height)
    box_width = max(1.0, x2 - x1)
    box_height = max(1.0, y2 - y1)
    pad_x = box_width * max(0.0, float(padding_ratio))
    pad_y = box_height * max(0.0, float(padding_ratio))
    return clamp_box([x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y], width, height)


def evidence_frame_ids(event: dict[str, Any], primary_frame_id: int) -> list[int]:
    result: list[int] = []
    for raw in event.get("evidence_frame_ids") or []:
        try:
            frame_id = max(0, int(raw))
        except (TypeError, ValueError):
            continue
        if frame_id not in result:
            result.append(frame_id)
    if primary_frame_id not in result:
        result.append(primary_frame_id)
    return result


def write_relation_context_crop(
    cv2: Any,
    frame: Any,
    event: dict[str, Any],
    output_path: Path,
    width: int,
    height: int,
    encode_params: list[int],
) -> tuple[Path | None, list[float] | None, list[str]]:
    boxes = get_event_boxes(event)
    if len(boxes) < 2:
        return None, None, []
    normalized: list[tuple[list[float], str]] = []
    for box in boxes:
        bbox = box.get("bbox_xyxy") or box.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        normalized.append(
            (
                clamp_box([float(value) for value in bbox[:4]], width, height),
                str(box.get("detection_id") or ""),
            )
        )
    if len(normalized) < 2:
        return None, None, []
    union = [
        min(item[0][0] for item in normalized),
        min(item[0][1] for item in normalized),
        max(item[0][2] for item in normalized),
        max(item[0][3] for item in normalized),
    ]
    context_box = expand_box(
        union,
        width,
        height,
        float(event.get("context_padding_ratio", 0.25)),
    )
    x1, y1, x2, y2 = [int(round(value)) for value in context_box]
    if x2 <= x1 or y2 <= y1:
        return None, None, []
    crop = frame[y1:y2, x1:x2]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), crop, encode_params):
        return None, None, []
    detection_ids = [detection_id for _, detection_id in normalized if detection_id]
    return output_path, context_box, detection_ids


def write_temporal_contact_sheet(
    cv2: Any,
    frames: list[tuple[int, Any]],
    output_path: Path,
    encode_params: list[int],
    panel_width: int = 640,
    panel_height: int = 360,
) -> Path | None:
    """Write ordered evidence frames as a compact 2-column image for single-image VLM runtimes."""
    valid_frames = [(frame_id, frame) for frame_id, frame in frames if frame is not None]
    if len(valid_frames) < 2:
        return None
    panels = []
    for frame_id, frame in valid_frames:
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            continue
        scale = min(panel_width / float(width), panel_height / float(height))
        resized_width = max(1, int(round(width * scale)))
        resized_height = max(1, int(round(height * scale)))
        resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
        left = (panel_width - resized_width) // 2
        right = panel_width - resized_width - left
        top = (panel_height - resized_height) // 2
        bottom = panel_height - resized_height - top
        panel = cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0),
        )
        cv2.putText(
            panel,
            f"frame {frame_id}",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        panels.append(panel)
    if len(panels) < 2:
        return None
    if len(panels) % 2:
        blank = panels[-1].copy()
        blank[:] = 0
        panels.append(blank)
    rows = [cv2.hconcat(panels[index : index + 2]) for index in range(0, len(panels), 2)]
    sheet = rows[0] if len(rows) == 1 else cv2.vconcat(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), sheet, encode_params):
        return None
    return output_path


@dataclass
class AssetStats:
    processed_events: int = 0
    success_events: int = 0
    degraded_events: int = 0
    keyframes_written: int = 0
    roi_images_written: int = 0
    context_crops_written: int = 0
    temporal_contact_sheets_written: int = 0


class NullAssetWorker:
    def __init__(self) -> None:
        self.stats = AssetStats()

    def enrich(self, event: dict[str, Any]) -> dict[str, Any]:
        return dict(event)

    def runtime_info(self) -> dict[str, Any]:
        return {"mode": "none"}

    def close(self) -> None:
        return


class FrameCacheAssetWorker:
    def __init__(
        self,
        source_uri: Path,
        asset_dir: Path,
        image_ext: str = "jpg",
        jpeg_quality: int = 92,
        frame_wait_timeout_sec: float = 2.0,
        poll_interval_sec: float = 0.05,
    ) -> None:
        self.source_uri = Path(source_uri)
        if self.source_uri.exists() and not self.source_uri.is_dir():
            raise SystemExit(f"frame cache source must be a directory: {self.source_uri}")
        self.source_uri.mkdir(parents=True, exist_ok=True)
        self.asset_dir = asset_dir
        self.image_ext = image_ext
        self.jpeg_quality = max(1, min(100, int(jpeg_quality)))
        self.frame_wait_timeout_sec = max(0.0, float(frame_wait_timeout_sec))
        self.poll_interval_sec = max(0.01, float(poll_interval_sec))
        self.stats = AssetStats()
        self.cv2 = require_cv2()
        self.keyframe_dir = self.asset_dir / "keyframes"
        self.roi_dir = self.asset_dir / "rois"
        self.context_dir = self.asset_dir / "context"
        self.keyframe_dir.mkdir(parents=True, exist_ok=True)
        self.roi_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.encode_params: list[int] = []
        if self.image_ext == "jpg":
            self.encode_params = [int(self.cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]

    def runtime_info(self) -> dict[str, Any]:
        return {
            "mode": "frame_cache",
            "source_type": "frame_cache_dir",
            "source_uri": str(self.source_uri),
            "asset_dir": str(self.asset_dir),
            "frame_wait_timeout_sec": self.frame_wait_timeout_sec,
        }

    def close(self) -> None:
        return

    def enrich(self, event: dict[str, Any]) -> dict[str, Any]:
        self.stats.processed_events += 1
        updated = dict(event)
        started = time.monotonic()
        frame_id = self._parse_frame_id(updated.get("frame_id"))
        if frame_id is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        frame = self._read_cached_frame(frame_id)
        if frame is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        keyframe_paths: list[str] = []
        evidence_frames: list[tuple[int, Any]] = []
        keyframe_path: Path | None = None
        for evidence_frame_id in evidence_frame_ids(updated, frame_id):
            evidence_frame = frame if evidence_frame_id == frame_id else self._read_cached_frame(evidence_frame_id)
            if evidence_frame is None:
                continue
            written = self._write_keyframe(updated, evidence_frame, evidence_frame_id)
            if written is None:
                continue
            keyframe_paths.append(str(written))
            evidence_frames.append((evidence_frame_id, evidence_frame))
            self.stats.keyframes_written += 1
            if evidence_frame_id == frame_id:
                keyframe_path = written
        if keyframe_path is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated
        height, width = frame.shape[:2]
        roi_paths, roi_boxes = self._write_rois(updated, frame, frame_id, width, height)
        self.stats.roi_images_written += len(roi_paths)

        context_path, context_box, context_detection_ids = write_relation_context_crop(
            self.cv2,
            frame,
            updated,
            self.context_dir / f"{safe_name(str(updated.get('event_id') or frame_id))}_context.{self.image_ext}",
            width,
            height,
            self.encode_params,
        )
        if context_path is not None:
            self.stats.context_crops_written += 1

        temporal_contact_sheet_path = write_temporal_contact_sheet(
            self.cv2,
            evidence_frames,
            self.context_dir / f"{safe_name(str(updated.get('event_id') or frame_id))}_temporal.{self.image_ext}",
            self.encode_params,
        )
        if temporal_contact_sheet_path is not None:
            self.stats.temporal_contact_sheets_written += 1

        updated["keyframe_path"] = str(keyframe_path)
        updated["keyframe_paths"] = keyframe_paths
        updated["roi_paths"] = roi_paths
        updated["roi_boxes"] = roi_boxes
        updated["context_crop_path"] = str(context_path) if context_path is not None else None
        updated["context_crop_box"] = context_box
        updated["context_detection_ids"] = context_detection_ids
        updated["temporal_contact_sheet_path"] = (
            str(temporal_contact_sheet_path) if temporal_contact_sheet_path is not None else None
        )
        updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
        if updated.get("status") == "degraded" and keyframe_path:
            updated["status"] = "not_verified"
        if updated.get("status") != "degraded":
            self.stats.success_events += 1
        else:
            self.stats.degraded_events += 1
        return updated

    def _parse_frame_id(self, raw: Any) -> int | None:
        try:
            frame_id = int(raw)
        except (TypeError, ValueError):
            return None
        return max(0, frame_id)

    def _frame_cache_path(self, frame_id: int) -> Path:
        return self.source_uri / f"frame_{frame_id:010d}.jpg"

    def _read_cached_frame(self, frame_id: int):
        deadline = time.monotonic() + self.frame_wait_timeout_sec
        frame_path = self._frame_cache_path(frame_id)
        while True:
            if frame_path.exists():
                frame = self.cv2.imread(str(frame_path), self.cv2.IMREAD_COLOR)
                if frame is not None and frame.size > 0:
                    return frame
            if time.monotonic() >= deadline:
                return None
            time.sleep(self.poll_interval_sec)

    def _write_keyframe(self, event: dict[str, Any], frame: Any, frame_id: int) -> Path | None:
        event_name = safe_name(str(event.get("event_id") or f"frame_{frame_id}"))
        keyframe_path = self.keyframe_dir / f"{event_name}_frame_{frame_id}.{self.image_ext}"
        if not self.cv2.imwrite(str(keyframe_path), frame, self.encode_params):
            return None
        return keyframe_path

    def _write_rois(
        self,
        event: dict[str, Any],
        frame: Any,
        frame_id: int,
        width: int,
        height: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        event_name = safe_name(str(event.get("event_id") or f"frame_{frame_id}"))
        roi_paths: list[str] = []
        roi_boxes_out: list[dict[str, Any]] = []
        for index, roi_box in enumerate(get_event_boxes(event)):
            bbox = roi_box.get("bbox_xyxy") or roi_box.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = expand_box(
                [float(v) for v in bbox[:4]],
                width,
                height,
                float(roi_box.get("padding", 0.05) or 0.0),
            )
            ix1 = int(max(0, min(width - 1, round(x1))))
            iy1 = int(max(0, min(height - 1, round(y1))))
            ix2 = int(max(0, min(width, round(x2))))
            iy2 = int(max(0, min(height, round(y2))))
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            crop = frame[iy1:iy2, ix1:ix2]
            roi_path = self.roi_dir / f"{event_name}_roi_{index:02d}.{self.image_ext}"
            if not self.cv2.imwrite(str(roi_path), crop, self.encode_params):
                continue
            roi_paths.append(str(roi_path))
            roi_boxes_out.append(
                {
                    "detection_id": roi_box.get("detection_id"),
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "coordinate_space": "source_frame",
                    "padding": roi_box.get("padding"),
                    "resized_to": roi_box.get("resized_to"),
                }
            )
        if not roi_boxes_out:
            fallback_boxes = []
            for roi_box in get_event_boxes(event):
                bbox = roi_box.get("bbox_xyxy") or roi_box.get("bbox")
                if bbox and len(bbox) >= 4:
                    x1, y1, x2, y2 = clamp_box([float(v) for v in bbox[:4]], width, height)
                    fallback_boxes.append(
                        {
                            "detection_id": roi_box.get("detection_id"),
                            "bbox_xyxy": [x1, y1, x2, y2],
                            "coordinate_space": "source_frame",
                            "padding": roi_box.get("padding"),
                            "resized_to": roi_box.get("resized_to"),
                        }
                    )
            roi_boxes_out = fallback_boxes or (event.get("roi_boxes") or [])
        return roi_paths, roi_boxes_out


class SourceMediaAssetWorker:
    def __init__(
        self,
        source_type: str,
        source_uri: Path,
        asset_dir: Path,
        image_ext: str = "jpg",
        jpeg_quality: int = 92,
        playlist_loop: bool = False,
        video_backend: str = "sequential",
        frame_index_dir: Path | None = None,
    ) -> None:
        self.source_type = source_type
        self.source_uri = source_uri
        self.asset_dir = asset_dir
        self.image_ext = image_ext
        self.jpeg_quality = max(1, min(100, int(jpeg_quality)))
        self.playlist_loop = playlist_loop
        if video_backend not in {"sequential", "indexed", "pyav"}:
            raise ValueError("unsupported event video backend")
        self.video_backend = video_backend
        self._indexed_reader = None
        self.last_read_metrics: dict[str, Any] = {}
        self.stats = AssetStats()
        self.cv2 = require_cv2()
        self.keyframe_dir = self.asset_dir / "keyframes"
        self.roi_dir = self.asset_dir / "rois"
        self.context_dir = self.asset_dir / "context"
        self.keyframe_dir.mkdir(parents=True, exist_ok=True)
        self.roi_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.encode_params: list[int] = []
        if self.image_ext == "jpg":
            self.encode_params = [int(self.cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        self._playlist_items: list[dict[str, Any]] = []
        self._playlist_total_frames = 0
        self._current_video_path: Path | None = None
        self._current_cap: Any = None
        self._current_orientation_mode = "none"
        self._next_frame_index = 0
        if video_backend in {"indexed", "pyav"}:
            from indexed_video_reader import IndexedVideoReader
            cache_dir = frame_index_dir or (Path(__file__).resolve().parents[4] / "data/cache/08_alarm_system/video_frame_indices_v1")
            if video_backend == "pyav":
                from direct_video_reader import create_direct_reader
                self._indexed_reader = create_direct_reader(cache_dir,
                    repository_root=Path(__file__).resolve().parents[4],
                    cv2_module=self.cv2, on_open=self._indexed_capture_open)
            else:
                self._indexed_reader = IndexedVideoReader(cache_dir, cv2_module=self.cv2,
                                                          on_open=self._indexed_capture_open)
        if self.source_type == "video_file":
            self._video_file = resolve_existing_path(str(self.source_uri))
        elif self.source_type == "video_playlist":
            self._video_file = None
            self._load_playlist_index(resolve_existing_path(str(self.source_uri)))
        else:
            raise SystemExit(
                f"unsupported AssetWorker source_type={self.source_type}; "
                "supported types are video_file and video_playlist"
            )

    def runtime_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "mode": "source_media",
            "source_type": self.source_type,
            "source_uri": str(self.source_uri),
            "asset_dir": str(self.asset_dir),
        }
        if self.source_type == "video_playlist":
            info["frame_access"] = self.video_backend
            info["playlist_loop"] = self.playlist_loop
            info["playlist_items"] = len(self._playlist_items)
            info["playlist_total_frames"] = self._playlist_total_frames
        if self.video_backend == "pyav":
            info["direct_backend_available"] = self._indexed_reader.direct_backend_available
        return info

    def close(self) -> None:
        if self._indexed_reader is not None:
            self._indexed_reader.close()
        if self._current_cap is not None:
            self._current_cap.release()
            self._current_cap = None
            self._current_video_path = None
            self._current_orientation_mode = "none"
        self._next_frame_index = 0

    def _indexed_capture_open(self, video_path: Path, cap: Any) -> None:
        self._current_orientation_mode = self._detect_orientation_correction(video_path, cap)

    def _read_requested_frames(self, requested: list[int]) -> dict[int, Any]:
        started = time.monotonic()
        decoded_frames = {}
        fallback = None
        groups = []
        if self._indexed_reader is not None:
            try:
                by_video: dict[Path, list[tuple[int, int]]] = {}
                for global_id in requested:
                    path, local = self._resolve_media_for_frame(global_id)
                    if path is None or local is None:
                        continue
                    by_video.setdefault(path, []).append((global_id, local))
                for path, pairs in by_video.items():
                    images = self._indexed_reader.read_many(path, [local for _, local in pairs])
                    groups.append(dict(self._indexed_reader.last_metrics))
                    for global_id, local in pairs:
                        decoded_frames[global_id] = self._apply_orientation_correction(images[local])
            except (OSError, ValueError, RuntimeError) as exc:
                fallback = str(exc)
                decoded_frames.clear()
                self.close()
        if self._indexed_reader is None or fallback is not None:
            for global_id in sorted(requested):
                path, local = self._resolve_media_for_frame(global_id)
                if path is not None and local is not None:
                    frame = self._read_frame(path, local)
                    if frame is not None:
                        decoded_frames[global_id] = frame
        self.last_read_metrics = dict(backend="sequential_fallback" if fallback else self.video_backend,
                                     source_read_ms=(time.monotonic() - started) * 1000,
                                     fallback_reason=fallback, groups=groups)
        return decoded_frames

    def enrich(self, event: dict[str, Any]) -> dict[str, Any]:
        self.stats.processed_events += 1
        updated = dict(event)
        started = time.monotonic()
        frame_id = self._parse_frame_id(updated.get("frame_id"))
        if frame_id is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        video_path, local_frame_id = self._resolve_media_for_frame(frame_id)
        if video_path is None or local_frame_id is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        # Read the few requested evidence frames in chronological order, once.
        # Primary-first reading would otherwise reopen and decode the same clip
        # again when the earlier confirmation-window evidence is requested.
        requested_frame_ids = evidence_frame_ids(updated, frame_id)
        decoded_frames = self._read_requested_frames(requested_frame_ids)
        frame = decoded_frames.get(frame_id)
        if frame is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        keyframe_paths: list[str] = []
        evidence_frames: list[tuple[int, Any]] = []
        keyframe_path: Path | None = None
        for evidence_frame_id in requested_frame_ids:
            evidence_frame = decoded_frames.get(evidence_frame_id)
            if evidence_frame is None:
                continue
            written = self._write_keyframe(updated, evidence_frame, evidence_frame_id)
            if written is None:
                continue
            keyframe_paths.append(str(written))
            evidence_frames.append((evidence_frame_id, evidence_frame))
            self.stats.keyframes_written += 1
            if evidence_frame_id == frame_id:
                keyframe_path = written
        if keyframe_path is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated
        height, width = frame.shape[:2]
        roi_paths, roi_boxes = self._write_rois(updated, frame, frame_id, width, height)
        self.stats.roi_images_written += len(roi_paths)

        context_path, context_box, context_detection_ids = write_relation_context_crop(
            self.cv2,
            frame,
            updated,
            self.context_dir / f"{safe_name(str(updated.get('event_id') or frame_id))}_context.{self.image_ext}",
            width,
            height,
            self.encode_params,
        )
        if context_path is not None:
            self.stats.context_crops_written += 1

        temporal_contact_sheet_path = write_temporal_contact_sheet(
            self.cv2,
            evidence_frames,
            self.context_dir / f"{safe_name(str(updated.get('event_id') or frame_id))}_temporal.{self.image_ext}",
            self.encode_params,
        )
        if temporal_contact_sheet_path is not None:
            self.stats.temporal_contact_sheets_written += 1

        updated["keyframe_path"] = str(keyframe_path)
        updated["keyframe_paths"] = keyframe_paths
        updated["roi_paths"] = roi_paths
        updated["roi_boxes"] = roi_boxes
        updated["context_crop_path"] = str(context_path) if context_path is not None else None
        updated["context_crop_box"] = context_box
        updated["context_detection_ids"] = context_detection_ids
        updated["temporal_contact_sheet_path"] = (
            str(temporal_contact_sheet_path) if temporal_contact_sheet_path is not None else None
        )
        updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
        if updated.get("status") == "degraded" and keyframe_path:
            updated["status"] = "not_verified"
        if updated.get("status") != "degraded":
            self.stats.success_events += 1
        else:
            self.stats.degraded_events += 1
        return updated

    def _parse_frame_id(self, raw: Any) -> int | None:
        try:
            frame_id = int(raw)
        except (TypeError, ValueError):
            return None
        return max(0, frame_id)

    def _load_playlist_index(self, playlist_path: Path) -> None:
        items: list[str] = []
        for raw_line in playlist_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.split("#", 1)[0].strip()
            if stripped:
                items.append(stripped)
        if not items:
            raise SystemExit(f"AssetWorker playlist is empty: {playlist_path}")

        cumulative = 0
        for item in items:
            video_path = resolve_existing_path(item, playlist_path)
            frame_count = self._probe_frame_count(video_path)
            if frame_count <= 0:
                raise SystemExit(f"AssetWorker failed to probe frame count: {video_path}")
            self._playlist_items.append(
                {
                    "path": video_path,
                    "frame_count": frame_count,
                    "start_frame": cumulative,
                    "end_frame": cumulative + frame_count,
                }
            )
            cumulative += frame_count
        self._playlist_total_frames = cumulative
        if self._playlist_total_frames <= 0:
            raise SystemExit(f"AssetWorker playlist has zero total frames: {playlist_path}")

    def _probe_frame_count(self, video_path: Path) -> int:
        cap = self.cv2.VideoCapture(str(video_path))
        try:
            if not cap.isOpened():
                return 0
            frame_count = int(round(float(cap.get(self.cv2.CAP_PROP_FRAME_COUNT))))
            return max(0, frame_count)
        finally:
            cap.release()

    def _resolve_media_for_frame(self, frame_id: int) -> tuple[Path | None, int | None]:
        if self.source_type == "video_file":
            return self._video_file, frame_id

        if self._playlist_total_frames <= 0:
            return None, None
        effective_frame = frame_id
        if effective_frame >= self._playlist_total_frames:
            if not self.playlist_loop:
                return None, None
            effective_frame = effective_frame % self._playlist_total_frames
        for item in self._playlist_items:
            if item["start_frame"] <= effective_frame < item["end_frame"]:
                local_frame = effective_frame - item["start_frame"]
                return item["path"], local_frame
        return None, None

    def _ensure_capture(self, video_path: Path) -> Any:
        if self._current_video_path == video_path and self._current_cap is not None:
            return self._current_cap
        self.close()
        cap = self.cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"AssetWorker failed to open video: {video_path}")
        self._current_video_path = video_path
        self._current_cap = cap
        self._current_orientation_mode = self._detect_orientation_correction(video_path, cap)
        return cap

    def _detect_orientation_correction(self, video_path: Path, cap: Any) -> str:
        # Match the detector's current auto-rotation contract for BDD100K MOV clips:
        # if the decoded frame is portrait, normalize it back to the detector's landscape space.
        source = str(video_path).replace("\\", "/")
        if "bdd100k_mot_mini_v1" not in source:
            return "none"
        width = int(round(float(cap.get(self.cv2.CAP_PROP_FRAME_WIDTH) or 0.0)))
        height = int(round(float(cap.get(self.cv2.CAP_PROP_FRAME_HEIGHT) or 0.0)))
        if width >= height or width <= 0 or height <= 0:
            return "none"
        orientation_meta_prop = int(getattr(self.cv2, "CAP_PROP_ORIENTATION_META", 48))
        rotation = int(round(float(cap.get(orientation_meta_prop) or 0.0)))
        rotation = ((rotation % 360) + 360) % 360
        return "counterclockwise" if rotation == 270 else "clockwise"

    def _apply_orientation_correction(self, frame: Any) -> Any:
        if frame is None:
            return None
        if self._current_orientation_mode == "clockwise":
            return self.cv2.rotate(frame, self.cv2.ROTATE_90_CLOCKWISE)
        if self._current_orientation_mode == "counterclockwise":
            return self.cv2.rotate(frame, self.cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self._current_orientation_mode == "rotate180":
            return self.cv2.rotate(frame, self.cv2.ROTATE_180)
        return frame

    def _read_frame(self, video_path: Path, frame_id: int):
        cap = self._ensure_capture(video_path)
        # CAP_PROP_POS_FRAMES random seeking did not reproduce the detector's
        # sequential frame indices on the real MOV playlist. Count actual
        # decoded frames instead; no FPS/time-based approximation or offset.
        if frame_id < self._next_frame_index:
            self.close()
            cap = self._ensure_capture(video_path)
        while self._next_frame_index < frame_id:
            if not cap.grab():
                return None
            self._next_frame_index += 1
        ok, frame = cap.read()
        if ok:
            self._next_frame_index += 1
        if ok:
            return self._apply_orientation_correction(frame)
        return None

    def _write_keyframe(self, event: dict[str, Any], frame: Any, frame_id: int) -> Path | None:
        event_name = safe_name(str(event.get("event_id") or f"frame_{frame_id}"))
        keyframe_path = self.keyframe_dir / f"{event_name}_frame_{frame_id}.{self.image_ext}"
        if not self.cv2.imwrite(str(keyframe_path), frame, self.encode_params):
            return None
        return keyframe_path

    def _write_rois(
        self,
        event: dict[str, Any],
        frame: Any,
        frame_id: int,
        width: int,
        height: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        event_name = safe_name(str(event.get("event_id") or f"frame_{frame_id}"))
        roi_paths: list[str] = []
        roi_boxes_out: list[dict[str, Any]] = []
        for index, roi_box in enumerate(get_event_boxes(event)):
            bbox = roi_box.get("bbox_xyxy") or roi_box.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = expand_box(
                [float(v) for v in bbox[:4]],
                width,
                height,
                float(roi_box.get("padding", 0.05) or 0.0),
            )
            ix1 = int(max(0, min(width - 1, round(x1))))
            iy1 = int(max(0, min(height - 1, round(y1))))
            ix2 = int(max(0, min(width, round(x2))))
            iy2 = int(max(0, min(height, round(y2))))
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            crop = frame[iy1:iy2, ix1:ix2]
            roi_path = self.roi_dir / f"{event_name}_roi_{index:02d}.{self.image_ext}"
            if not self.cv2.imwrite(str(roi_path), crop, self.encode_params):
                continue
            roi_paths.append(str(roi_path))
            roi_boxes_out.append(
                {
                    "detection_id": roi_box.get("detection_id"),
                    "bbox_xyxy": [x1, y1, x2, y2],
                    "coordinate_space": "source_frame",
                    "padding": roi_box.get("padding"),
                    "resized_to": roi_box.get("resized_to"),
                }
            )
        if not roi_boxes_out:
            fallback_boxes = []
            for roi_box in get_event_boxes(event):
                bbox = roi_box.get("bbox_xyxy") or roi_box.get("bbox")
                if bbox and len(bbox) >= 4:
                    x1, y1, x2, y2 = clamp_box([float(v) for v in bbox[:4]], width, height)
                    fallback_boxes.append(
                        {
                            "detection_id": roi_box.get("detection_id"),
                            "bbox_xyxy": [x1, y1, x2, y2],
                            "coordinate_space": "source_frame",
                            "padding": roi_box.get("padding"),
                            "resized_to": roi_box.get("resized_to"),
                        }
                    )
            roi_boxes_out = fallback_boxes or (event.get("roi_boxes") or [])
        return roi_paths, roi_boxes_out
