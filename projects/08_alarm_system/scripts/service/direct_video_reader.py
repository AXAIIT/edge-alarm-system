"""Qualified direct-demux reader; unsupported inputs retain the indexed fallback."""
from bisect import bisect_right
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

from indexed_video_reader import IndexedVideoReader


class PyavReader(IndexedVideoReader):
    def __init__(self, *args, runtime, decoder_threads=6, thread_type="FRAME", **kwargs):
        super().__init__(*args, **kwargs)
        self.direct_backend_available = True
        self.av = runtime["av"]
        self.approved_sources = set(runtime["approved_source_sha256"])
        self.decoder_threads = decoder_threads
        self.thread_type = thread_type
        self.container = self.stream = None
        self.orientation_angle = 0
        self.fallback = IndexedVideoReader(self.cache_dir, cv2_module=self.cv2, on_open=self.on_open)
        self.fallback.indices = self.indices  # One shared LRU, not two copies.

    def _capture(self, video_path):
        path = video_path.resolve()
        if self.container is None or self.video_path != path:
            self.close_capture()
            # Match both OpenCV automatic display rotation and Source correction.
            probe = self.cv2.VideoCapture(str(path))
            try:
                if not probe.isOpened():
                    raise RuntimeError("Cannot open orientation-contract probe")
                angle = int(round(probe.get(self.cv2.CAP_PROP_ORIENTATION_META))) % 360
                self.orientation_angle = angle if probe.get(self.cv2.CAP_PROP_ORIENTATION_AUTO) else 0
                if self.orientation_angle not in (0, 90, 180, 270):
                    raise ValueError("Unsupported exact display rotation")
                if self.on_open is not None:
                    self.on_open(path, probe)
            finally:
                probe.release()
            self.container = self.av.open(str(path))
            self.stream = self.container.streams.video[0]
            self.stream.thread_type = self.thread_type
            self.stream.codec_context.thread_count = self.decoder_threads
            self.video_path = path
        return self.container

    def _direct_read_many(self, video_path, frame_ids):
        began = time.monotonic()
        targets = sorted(set(frame_ids))
        if not targets:
            return {}
        index = self.index(video_path)
        metrics = dict(self.last_metrics)
        if index["source_sha256"] not in self.approved_sources:
            raise ValueError("Source not qualified for the direct decoder")
        if targets[0] < 0 or targets[-1] >= len(index["timestamps_us"]):
            raise ValueError("Requested frame outside exact index")
        keys = index["i_frame_indices"]
        anchor = lambda target: keys[max(0, bisect_right(keys, target) - 1)]
        plans = [[targets[0]]]
        for target in targets[1:]:
            if target - plans[-1][-1] <= 24 or anchor(target) <= plans[-1][-1]:
                plans[-1].append(target)
            else:
                plans.append([target])
        frames, segments = {}, []
        phases = dict(open_ms=0., seek_ms=0., grab_ms=0., retrieve_ms=0.)
        for requested in plans:
            # Early repeated PTS are ambiguous after seek: count from a fresh file.
            from_start = requested[0] < max(32, keys[min(2, len(keys) - 1)])
            if from_start:
                self.close_capture()
            start = time.monotonic()
            container = self._capture(video_path)
            phases["open_ms"] += (time.monotonic() - start) * 1000
            start = time.monotonic()
            if not from_start:
                pts = int(round(index["timestamps_us"][requested[0]] / 1e6 / float(self.stream.time_base)))
                container.seek(pts, stream=self.stream, backward=True, any_frame=False)
            phases["seek_ms"] += (time.monotonic() - start) * 1000
            wanted, found = set(requested), set()
            decoded, first, previous = 0, None, None
            iterator = iter(container.decode(self.stream))
            while True:
                start = time.monotonic()
                try:
                    frame = next(iterator)
                except StopIteration:
                    break
                phases["grab_ms"] += (time.monotonic() - start) * 1000
                if frame.pts is None:
                    raise ValueError("Decoded PTS missing")
                stamp = round(float(frame.pts * frame.time_base) * 1e6)
                actual = decoded if from_start else index["timestamp_to_index"].get(stamp)
                decoded += 1
                if actual is None or actual >= len(index["timestamps_us"]):
                    raise ValueError("Ambiguous/unrecognized direct-decoder timestamp")
                if stamp != index["timestamps_us"][actual]:
                    raise ValueError("Direct-decoder timestamp differs from exact source index")
                if previous is not None and actual != previous + 1:
                    raise ValueError("Non-sequential direct-decoder timestamp mapping")
                if first is None:
                    first = actual
                    if actual > requested[0]:
                        raise ValueError("Direct seek overshot earliest target")
                previous = actual
                if actual in wanted:
                    start = time.monotonic()
                    image = frame.to_ndarray(format="bgr24")
                    if self.orientation_angle:
                        flags = {90: self.cv2.ROTATE_90_CLOCKWISE, 180: self.cv2.ROTATE_180,
                                 270: self.cv2.ROTATE_90_COUNTERCLOCKWISE}
                        image = self.cv2.rotate(image, flags[self.orientation_angle])
                    phases["retrieve_ms"] += (time.monotonic() - start) * 1000
                    frames[actual] = image
                    found.add(actual)
                if found == wanted or actual > requested[-1] or decoded > len(index["timestamps_us"]):
                    break
            if found != wanted:
                raise ValueError("Exact direct-decoder target frames missing")
            segments.append(dict(from_start=from_start, first_observed_frame=first,
                                 requested_frame_ids=requested, decoded_frames=decoded))
        if set(frames) != set(targets):
            raise ValueError("Incomplete exact frame set")
        self.last_metrics = dict(metrics, backend="pyav_direct", decoder_threads=self.decoder_threads,
                                 thread_type=self.thread_type, av_version=self.av.__version__,
                                 av_library_versions=self.av.library_versions, phases=phases, segments=segments,
                                 requested_frame_ids=targets, decoded_frames=sum(s["decoded_frames"] for s in segments),
                                 total_ms=(time.monotonic() - began) * 1000)
        return frames

    def read_many(self, video_path, frame_ids):
        began = time.monotonic()
        self.fallback.close_capture()
        try:
            return self._direct_read_many(video_path, frame_ids)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError, IndexError) as exc:
            # PyAV's FFmpeg errors inherit OSError; never substitute a nearby frame.
            self.close_capture()
            try:
                result = self.fallback.read_many(video_path, frame_ids)
            except (KeyError, TypeError, AttributeError, IndexError) as fallback_exc:
                # A malformed metadata index must reach Source's exact sequential
                # fallback, not escape as an unexpected Python structure error.
                raise ValueError("Malformed exact frame-index metadata") from fallback_exc
            self.last_metrics = dict(self.fallback.last_metrics, backend="opencv_indexed_fallback",
                                     direct_fallback_reason=str(exc),
                                     total_ms=(time.monotonic()-began)*1000)
            return result

    def close_capture(self):
        if self.container is not None:
            self.container.close()
        self.container = self.stream = self.video_path = None
        self.orientation_angle = 0

    def close(self):
        super().close()
        self.fallback.close_capture()


def load_qualified_runtime(repository_root, cv2_module):
    root = Path(repository_root).resolve()
    run = root / "projects/08_alarm_system/runs/20261013_jetson_8gb_project08_sparse_event_assets_v1"
    approval = run / "analysis/direct_reader_approval.json"
    if not approval.is_file():
        return None
    try:
        data = json.loads(approval.read_text(encoding="utf-8"))
        fingerprint = hashlib.sha256(cv2_module.getBuildInformation().encode()).hexdigest()
        if data["opencv_fingerprint"] != fingerprint or not data["quality_passed"]:
            return None
        dependency = (root / data["dependency_root"]).resolve()
        dependency.relative_to(root)
        for rel, digest in data["dependency_sha256"].items():
            path = (dependency / rel).resolve()
            path.relative_to(dependency)
            check = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024*1024), b""):
                    check.update(block)
            if check.hexdigest() != digest:
                return None
        sys.path.insert(0, str(dependency))
        try:
            av = importlib.import_module("av")
        finally:
            sys.path.remove(str(dependency))
        Path(av.__file__).resolve().relative_to(dependency)
        if av.__version__ != data["av_version"]:
            return None
        if {k: list(v) for k, v in av.library_versions.items()} != data["av_library_versions"]:
            return None
        assert len(data["approved_source_sha256"]) == 20
        return dict(data, av=av)
    except (ImportError, OSError, ValueError, KeyError, TypeError, AssertionError):
        return None


def create_direct_reader(cache_dir, *, repository_root, cv2_module, on_open=None):
    runtime = load_qualified_runtime(repository_root, cv2_module)
    if runtime is None:
        reader = IndexedVideoReader(cache_dir, cv2_module=cv2_module, on_open=on_open)
        reader.direct_backend_available = False
        return reader
    return PyavReader(cache_dir, runtime=runtime, cv2_module=cv2_module, on_open=on_open)
