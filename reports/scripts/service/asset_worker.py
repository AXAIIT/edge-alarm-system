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
            "OpenCV python package is required for Project5 AssetWorker: "
            "install python3-opencv or run inside the Project3/Project5 runtime env"
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


@dataclass
class AssetStats:
    processed_events: int = 0
    success_events: int = 0
    degraded_events: int = 0
    keyframes_written: int = 0
    roi_images_written: int = 0


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
        self.keyframe_dir.mkdir(parents=True, exist_ok=True)
        self.roi_dir.mkdir(parents=True, exist_ok=True)
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

        keyframe_path = self._write_keyframe(updated, frame, frame_id)
        if keyframe_path is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated
        self.stats.keyframes_written += 1

        height, width = frame.shape[:2]
        roi_paths, roi_boxes = self._write_rois(updated, frame, frame_id, width, height)
        self.stats.roi_images_written += len(roi_paths)

        updated["keyframe_path"] = str(keyframe_path)
        updated["roi_paths"] = roi_paths
        updated["roi_boxes"] = roi_boxes
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
            x1, y1, x2, y2 = clamp_box([float(v) for v in bbox[:4]], width, height)
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
    ) -> None:
        self.source_type = source_type
        self.source_uri = source_uri
        self.asset_dir = asset_dir
        self.image_ext = image_ext
        self.jpeg_quality = max(1, min(100, int(jpeg_quality)))
        self.playlist_loop = playlist_loop
        self.stats = AssetStats()
        self.cv2 = require_cv2()
        self.keyframe_dir = self.asset_dir / "keyframes"
        self.roi_dir = self.asset_dir / "rois"
        self.keyframe_dir.mkdir(parents=True, exist_ok=True)
        self.roi_dir.mkdir(parents=True, exist_ok=True)
        self.encode_params: list[int] = []
        if self.image_ext == "jpg":
            self.encode_params = [int(self.cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        self._playlist_items: list[dict[str, Any]] = []
        self._playlist_total_frames = 0
        self._current_video_path: Path | None = None
        self._current_cap: Any = None
        self._current_orientation_mode = "none"
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
            info["playlist_loop"] = self.playlist_loop
            info["playlist_items"] = len(self._playlist_items)
            info["playlist_total_frames"] = self._playlist_total_frames
        return info

    def close(self) -> None:
        if self._current_cap is not None:
            self._current_cap.release()
            self._current_cap = None
            self._current_video_path = None
            self._current_orientation_mode = "none"

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

        frame = self._read_frame(video_path, local_frame_id)
        if frame is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated

        keyframe_path = self._write_keyframe(updated, frame, frame_id)
        if keyframe_path is None:
            updated["status"] = "degraded"
            updated["roi_crop_latency_ms"] = round((time.monotonic() - started) * 1000.0, 3)
            self.stats.degraded_events += 1
            return updated
        self.stats.keyframes_written += 1

        height, width = frame.shape[:2]
        roi_paths, roi_boxes = self._write_rois(updated, frame, frame_id, width, height)
        self.stats.roi_images_written += len(roi_paths)

        updated["keyframe_path"] = str(keyframe_path)
        updated["roi_paths"] = roi_paths
        updated["roi_boxes"] = roi_boxes
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
        cap.set(self.cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = cap.read()
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
            x1, y1, x2, y2 = clamp_box([float(v) for v in bbox[:4]], width, height)
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
