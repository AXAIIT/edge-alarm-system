#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from queue import Full, Queue
from typing import Any


@dataclass
class QueueStats:
    enqueued: int = 0
    dequeued: int = 0
    dropped: int = 0
    max_depth: int = 0


class BoundedEventQueue:
    def __init__(self, capacity: int, drop_policy: str = "drop_newest") -> None:
        self.queue: Queue[dict[str, Any] | None] = Queue(maxsize=max(1, capacity))
        self.drop_policy = drop_policy
        self.stats = QueueStats()

    def put_event(self, event: dict[str, Any]) -> bool:
        try:
            self.queue.put_nowait(event)
        except Full:
            self.stats.dropped += 1
            return False
        self.stats.enqueued += 1
        self.stats.max_depth = max(self.stats.max_depth, self.queue.qsize())
        return True

    def get(self) -> dict[str, Any] | None:
        item = self.queue.get()
        if item is not None:
            self.stats.dequeued += 1
        return item

    def stop(self) -> None:
        self.queue.put(None)

    def task_done(self) -> None:
        self.queue.task_done()

    def depth(self) -> int:
        return self.queue.qsize()
