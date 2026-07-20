#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8", newline="\n")
        self.count = 0

    def write(self, row: dict[str, Any]) -> None:
        self.handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.handle.flush()
        self.count += 1

    def close(self) -> None:
        self.handle.close()
