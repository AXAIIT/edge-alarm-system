#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import read_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Project 05 detector adapter. For formal board runs, prefer invoking the Project 03 "
            "C++ service directly and point --project3-raw to its JSONL output for normalization."
        )
    )
    parser.add_argument("--board-config", required=True, type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--project3-config", default="")
    parser.add_argument("--project3-raw", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()

    if args.project3_raw is None:
        raise SystemExit(
            "--project3-raw is required for this adapter. Run the Project 03 detector service first "
            "or pass an existing Project 03 frame-level JSONL for interface wiring."
        )
    rows = read_jsonl(args.project3_raw)
    if args.max_frames:
        rows = rows[: args.max_frames]
    count = write_jsonl(args.output, rows)
    print(f"detector_rows_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
