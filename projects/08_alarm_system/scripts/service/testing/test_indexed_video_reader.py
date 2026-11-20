"""Exact image identity, cache binding and fallback tests; no model loading."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from indexed_video_reader import IndexedVideoReader
from asset_worker import SourceMediaAssetWorker

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None


@unittest.skipIf(cv2 is None, "OpenCV unavailable")
class IndexedReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p08-cv-index-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = [self.root / "a.avi", self.root / "b.avi"]
        for index, path in enumerate(self.paths):
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (96, 64))
            self.assertTrue(writer.isOpened())
            for frame_id in range(14):
                frame = np.full((64, 96, 3), 10 + frame_id * 10 + index * 5, dtype=np.uint8)
                frame[8:24, 8:24] = (200, 20, frame_id * 10)
                writer.write(frame)
            writer.release()
        self.playlist = self.root / "playlist.txt"
        self.playlist.write_text("a.avi\nb.avi\n", encoding="utf-8")
        self.reader = IndexedVideoReader(self.root / "index")
        self.addCleanup(self.reader.close)

    def teacher(self, path, ids):
        frames = {}
        cap = cv2.VideoCapture(str(path))
        i = 0
        while cap.grab():
            if i in ids:
                ok, frames[i] = cap.retrieve()
                self.assertTrue(ok)
            i += 1
        cap.release()
        return frames

    def test_prefix_middle_end_and_backward_requests_match_exact_pixels(self):
        for ids in [[0, 1, 2], [5, 6, 7], [11, 12, 13], [3, 4, 5]]:
            actual = self.reader.read_many(self.paths[0], ids)
            expected = self.teacher(self.paths[0], ids)
            self.assertTrue(all(np.array_equal(actual[i], expected[i]) for i in ids))

    def test_clip_switch_preserves_pixels_and_bounded_index_lru(self):
        for path in self.paths + self.paths:
            actual = self.reader.read_many(path, [8, 10, 12])
            expected = self.teacher(path, [8, 10, 12])
            self.assertTrue(all(np.array_equal(actual[i], expected[i]) for i in actual))
        self.assertLessEqual(len(self.reader.indices), 2)

    def test_second_process_uses_bound_disk_index_without_rebuild(self):
        data = self.reader.index(self.paths[0])
        self.reader.close()
        data_again = self.reader.index(self.paths[0])
        self.assertEqual(data["timestamps_us"], data_again["timestamps_us"])
        self.assertTrue(self.reader.last_metrics["index_cache_hit"])
        self.assertEqual(self.reader.last_metrics["index_build_ms"], 0)

    def test_tampered_source_digest_is_rejected(self):
        data = self.reader.index(self.paths[0])
        cache = Path(data["cache_path"])
        obj = json.loads(cache.read_text(encoding="utf-8"))
        obj["source_sha256"] = "0" * 64
        cache.write_text(json.dumps(obj), encoding="utf-8")
        self.reader.close()
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.reader.index(self.paths[0])

    def test_out_of_range_is_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, "outside exact index"):
            self.reader.read_many(self.paths[0], [14])

    def event(self, frame_id=17, evidence=None):
        return dict(event_id="indexed_fixture", frame_id=frame_id, status="not_verified",
                    evidence_frame_ids=evidence or [3, 12, 17], alarm_type="multi_object_scene",
                    vlm_input_mode="relation_context_crop", detections=[
                        dict(detection_id="one", bbox=[5, 5, 25, 25]),
                        dict(detection_id="two", bbox=[40, 20, 75, 50])])

    def pair(self, event):
        a = SourceMediaAssetWorker("video_playlist", self.playlist, self.root / "A", playlist_loop=True)
        b = SourceMediaAssetWorker("video_playlist", self.playlist, self.root / "B", playlist_loop=True,
                                   video_backend="indexed", frame_index_dir=self.root / "worker_index")
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        return a, b

    def assert_assets_identical(self, a, b):
        def paths(event):
            return event["keyframe_paths"] + event["roi_paths"] + [event["context_crop_path"], event["temporal_contact_sheet_path"]]
        self.assertEqual(len(paths(a)), len(paths(b)))
        for x, y in zip(paths(a), paths(b)):
            self.assertEqual(Path(x).read_bytes(), Path(y).read_bytes())

    def test_full_asset_bytes_match_across_clip_boundary(self):
        event = self.event()
        a, b = self.pair(event)
        before = copy.deepcopy(event)
        self.assert_assets_identical(a.enrich(event), b.enrich(event))
        self.assertEqual(before, event)
        self.assertIsNone(b.last_read_metrics["fallback_reason"])

    def test_playlist_wrap_preserves_evidence_order_and_images(self):
        event = self.event(31, [27, 28, 31])
        a, b = self.pair(event)
        self.assert_assets_identical(a.enrich(event), b.enrich(event))

    def test_indexed_failure_uses_exact_sequential_without_missing_images(self):
        event = self.event()
        a, b = self.pair(event)
        with patch.object(b._indexed_reader, "read_many", side_effect=ValueError("unknown timestamp")):
            self.assert_assets_identical(a.enrich(event), b.enrich(event))
        self.assertEqual(b.last_read_metrics["backend"], "sequential_fallback")
        self.assertIn("unknown timestamp", b.last_read_metrics["fallback_reason"])


if __name__ == "__main__":
    unittest.main()
