"""Same-decoder timestamp index, keyframe-near seek and strict frame identity.

Stores metadata, never images. Unknown timestamps fail to the exact sequential
fallback; no average-fps frame conversion is accepted as identity evidence.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter, OrderedDict
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable


class IndexedVideoReader:
    def __init__(self, cache_dir: Path, *, cv2_module: Any = None,
                 on_open: Callable[[Path, Any], None] | None = None) -> None:
        if cv2_module is None:
            import cv2 as cv2_module
        self.cv2 = cv2_module
        self.on_open = on_open
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.decoder_fingerprint = hashlib.sha256(self.cv2.getBuildInformation().encode()).hexdigest()
        self.indices: OrderedDict[Path, tuple[tuple[int, int], dict[str, Any]]] = OrderedDict()
        self.cap = None
        self.video_path = None
        self.last_metrics: dict[str, Any] = {}

    def index(self, video_path: Path) -> dict[str, Any]:
        path = video_path.resolve()
        stat = path.stat()
        identity = (stat.st_size, stat.st_mtime_ns)
        prior = self.indices.get(path)
        if prior is not None and prior[0] == identity:
            self.indices.move_to_end(path)
            self.last_metrics = dict(index_cache_hit=True, index_build_ms=0, index_load_ms=0,
                                     index_file=prior[1]["cache_path"],
                                     index_bytes=Path(prior[1]["cache_path"]).stat().st_size)
            return prior[1]
        started = time.monotonic()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        cache = self.cache_dir / (digest.hexdigest() + "_" + self.decoder_fingerprint[:16] + "_cvpts_v1.json")
        cached = cache.is_file()
        build_ms = 0.0
        if cached:
            if cache.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("frame-index metadata budget exceeded")
            data = json.loads(cache.read_text(encoding="utf-8"))
            if (data.get("version") != 1 or data.get("source_sha256") != digest.hexdigest()
                    or data.get("decoder_fingerprint") != self.decoder_fingerprint):
                raise ValueError("frame-index source/decoder identity mismatch")
        else:
            build_start = time.monotonic()
            cap = self.cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise RuntimeError("Cannot open video to build frame index")
            timestamps, keys = [], []
            try:
                while cap.grab():
                    i = len(timestamps)
                    if i >= 250000:
                        raise ValueError("frame index exceeds length budget")
                    timestamps.append(int(round(cap.get(self.cv2.CAP_PROP_POS_MSEC) * 1000)))
                    if cap.get(getattr(self.cv2, "CAP_PROP_FRAME_TYPE", 69)) == ord("I"):
                        keys.append(i)
            finally:
                cap.release()
            if not timestamps or not keys:
                raise ValueError("Decoder does not expose required timestamp/I-frame metadata")
            data = dict(version=1, source_sha256=digest.hexdigest(),
                        decoder_fingerprint=self.decoder_fingerprint,
                        opencv_version=self.cv2.__version__, timestamps_us=timestamps, i_frame_indices=keys)
            encoded = json.dumps(data, separators=(",", ":"))
            if len(encoded) > 16 * 1024 * 1024:
                raise ValueError("frame-index metadata budget exceeded")
            try:
                with cache.open("x", encoding="utf-8") as handle:
                    handle.write(encoded)
            except FileExistsError:
                if json.loads(cache.read_text(encoding="utf-8")) != data:
                    raise ValueError("Conflicting concurrent frame index")
            build_ms = (time.monotonic() - build_start) * 1000
        counts = Counter(data["timestamps_us"])
        data["timestamp_to_index"] = {ts: i for i, ts in enumerate(data["timestamps_us"]) if counts[ts] == 1}
        data["cache_path"] = str(cache)
        self.indices[path] = (identity, data)
        self.indices.move_to_end(path)
        while len(self.indices) > 2:
            self.indices.popitem(last=False)
        self.last_metrics = dict(index_cache_hit=cached, index_build_ms=build_ms,
                                 index_load_ms=(time.monotonic() - started) * 1000,
                                 index_file=str(cache), index_bytes=cache.stat().st_size)
        return data

    def _capture(self, video_path: Path):
        path = video_path.resolve()
        if self.cap is None or self.video_path != path:
            self.close_capture()
            self.cap = self.cv2.VideoCapture(str(path))
            if not self.cap.isOpened():
                self.close_capture()
                raise RuntimeError("Cannot open indexed video capture")
            self.video_path = path
            if self.on_open is not None:
                self.on_open(path, self.cap)
        return self.cap

    def read_many(self, video_path: Path, frame_ids: list[int]) -> dict[int, Any]:
        started = time.monotonic()
        targets = sorted(set(frame_ids))
        if not targets:
            return {}
        index = self.index(video_path)
        metrics = dict(self.last_metrics)
        if targets[0] < 0 or targets[-1] >= len(index["timestamps_us"]):
            raise ValueError("Requested frame outside exact index")
        key_location = bisect_right(index["i_frame_indices"], targets[0]) - 1
        # Seek one I-frame earlier; never trust the approximate landing index.
        anchor = index["i_frame_indices"][max(0, key_location - 1)] if key_location >= 1 else 0
        if anchor == 0:
            self.close_capture()
        cap = self._capture(video_path)
        if anchor and not cap.set(self.cv2.CAP_PROP_POS_MSEC, max(0, index["timestamps_us"][anchor]) / 1000):
            raise RuntimeError("Decoder rejected indexed seek")
        frames = {}
        decoded = 0
        first_observed = None
        previous = None
        target_set = set(targets)
        while cap.grab():
            stamp = int(round(cap.get(self.cv2.CAP_PROP_POS_MSEC) * 1000))
            actual = decoded if anchor == 0 else index["timestamp_to_index"].get(stamp)
            decoded += 1
            if actual is None:
                raise ValueError("Ambiguous/unrecognized decoded timestamp after seek")
            if previous is not None and actual != previous + 1:
                raise ValueError("Non-sequential timestamp mapping after seek")
            if first_observed is None:
                first_observed = actual
                if actual > targets[0]:
                    raise ValueError("Seek overshot earliest requested frame")
            previous = actual
            if actual in target_set:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    raise RuntimeError("Cannot retrieve indexed target frame")
                frames[actual] = frame
            if len(frames) == len(targets):
                break
            if actual > targets[-1] or decoded > len(index["timestamps_us"]):
                break
        if set(frames) != target_set:
            raise ValueError("Exact indexed target frames missing")
        self.last_metrics = dict(metrics, backend="indexed_opencv_timestamp", video_path=str(video_path),
                                 requested_frame_ids=targets, anchor_frame=anchor,
                                 first_observed_frame=first_observed, decoded_frames=decoded,
                                 total_ms=(time.monotonic() - started) * 1000)
        return frames

    def close_capture(self) -> None:
        if self.cap is not None:
            self.cap.release()
        self.cap = self.video_path = None

    def close(self) -> None:
        self.close_capture()
        self.indices.clear()
