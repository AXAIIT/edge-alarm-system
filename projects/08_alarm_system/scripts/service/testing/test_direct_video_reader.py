"""Host-testable exact compatibility and direct-error safety, no real AV needed."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from indexed_video_reader import IndexedVideoReader
from direct_video_reader import PyavReader, create_direct_reader
import cv2
import numpy as np
from asset_worker import SourceMediaAssetWorker


class DirectSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="p08-direct-safety-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "source.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (96, 64))
        self.assertTrue(writer.isOpened())
        for i in range(14):
            writer.write(np.full((64, 96, 3), i*12+5, dtype=np.uint8))
        writer.release()
        self.teacher = IndexedVideoReader(self.root / "cache")
        self.addCleanup(self.teacher.close)

    def fake_av(self):
        def bad_open(*args, **kwargs):
            raise OSError("direct decoder deliberately unavailable")
        return SimpleNamespace(open=bad_open, __version__="12.3.0", library_versions={})

    def reader(self, approved):
        reader = PyavReader(self.root / "cache", runtime=dict(av=self.fake_av(), approved_source_sha256=approved))
        self.addCleanup(reader.close)
        return reader

    def test_missing_runtime_preserves_current_indexed_reader(self):
        reader = create_direct_reader(self.root / "cache", repository_root=self.root, cv2_module=cv2)
        self.addCleanup(reader.close)
        self.assertIsInstance(reader, IndexedVideoReader)
        self.assertFalse(reader.direct_backend_available)

    def test_unqualified_source_keeps_exact_indexed_images(self):
        reader = self.reader([])
        expected = self.teacher.read_many(self.video, [3, 8, 12])
        actual = reader.read_many(self.video, [3, 8, 12])
        self.assertTrue(all(np.array_equal(expected[i], actual[i]) for i in expected))
        self.assertIn("not qualified", reader.last_metrics["direct_fallback_reason"])

    def test_direct_decoder_error_falls_back_without_losing_targets(self):
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        reader = self.reader([digest])
        expected = self.teacher.read_many(self.video, [3, 8, 12])
        actual = reader.read_many(self.video, [3, 8, 12])
        self.assertTrue(all(np.array_equal(expected[i], actual[i]) for i in expected))
        self.assertIn("deliberately unavailable", reader.last_metrics["direct_fallback_reason"])

    def test_out_of_range_is_rejected_even_after_direct_fallback(self):
        reader = self.reader([])
        with self.assertRaisesRegex(ValueError, "outside exact index"):
            reader.read_many(self.video, [14])

    def test_two_backends_share_one_bounded_metadata_lru(self):
        reader = self.reader([])
        reader.read_many(self.video, [3, 8, 12])
        self.assertIs(reader.indices, reader.fallback.indices)
        self.assertLessEqual(len(reader.indices), 2)
        reader.close()
        self.assertEqual(len(reader.indices), 0)

    def test_malformed_metadata_reaches_exact_source_fallback(self):
        reader = self.reader([])
        index = self.teacher.index(self.video)
        cache = Path(index["cache_path"])
        cache.write_text("[]", encoding="utf-8")
        with mock.patch("direct_video_reader.create_direct_reader", return_value=reader):
            worker = SourceMediaAssetWorker("video_file", self.video, self.root / "assets",
                                           video_backend="pyav", frame_index_dir=self.root / "cache")
        self.addCleanup(worker.close)
        expected = self.teacher.read_many(self.video, [3, 8, 12])
        actual = worker._read_requested_frames([3, 8, 12])
        self.assertEqual(worker.last_read_metrics["backend"], "sequential_fallback")
        self.assertIn("Malformed exact", worker.last_read_metrics["fallback_reason"])
        self.assertTrue(all(np.array_equal(expected[i], actual[i]) for i in expected))


if __name__ == "__main__":
    unittest.main()
