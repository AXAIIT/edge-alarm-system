#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def build_row(run_id: str, frame_id: int, board: str, target: str) -> dict:
    return {
        "run_id": run_id,
        "timestamp": "2026-07-09T00:00:00+00:00",
        "schema_version": 1,
        "project": "05_alarm_system",
        "measurement_scope": "frame",
        "board": board,
        "target": target,
        "input_source_id": "project5_fake_resident_detector",
        "input_width": 1280,
        "input_height": 720,
        "frame_id": frame_id,
        "capture_ts": "2026-07-09T00:00:00+00:00",
        "output_ts": "2026-07-09T00:00:00+00:00",
        "end_to_end_latency_ms": 10.0,
        "queue_capture_size": 0,
        "queue_preprocess_size": 0,
        "queue_infer_size": 0,
        "queue_postprocess_size": 0,
        "queue_policy": "drop_oldest",
        "detections": [
            {
                "class_id": 0,
                "class_name": "person",
                "confidence": 0.82,
                "bbox": [100.0, 120.0, 260.0, 520.0],
            },
            {
                "class_id": 2,
                "class_name": "car",
                "confidence": 0.76,
                "bbox": [520.0, 260.0, 880.0, 560.0],
            },
        ],
        "runtime_log_path": None,
        "failure_log_path": None,
        "runtime_evidence_path": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project 05 local fake resident detector for service-mode smoke.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--board", default="PC")
    parser.add_argument("--target", default="pc")
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--sleep-ms", type=float, default=10.0)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for frame_id in range(args.frames):
            handle.write(json.dumps(build_row(args.run_id, frame_id, args.board, args.target), ensure_ascii=False) + "\n")
            handle.flush()
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
