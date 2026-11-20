#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable


def _read_meminfo() -> dict[str, float | None]:
    path = Path("/proc/meminfo")
    if not path.exists():
        return {"available_ram_mb": None, "swap_used_mb": None}
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0])
    available_kb = values.get("MemAvailable")
    swap_total_kb = values.get("SwapTotal")
    swap_free_kb = values.get("SwapFree")
    swap_used_kb = None
    if swap_total_kb is not None and swap_free_kb is not None:
        swap_used_kb = max(0, swap_total_kb - swap_free_kb)
    return {
        "available_ram_mb": round(available_kb / 1024.0, 3) if available_kb is not None else None,
        "swap_used_mb": round(swap_used_kb / 1024.0, 3) if swap_used_kb is not None else None,
    }


def _read_temperature_c() -> float | None:
    values: list[float] = []
    thermal_root = Path("/sys/class/thermal")
    if thermal_root.exists():
        for path in thermal_root.glob("thermal_zone*/temp"):
            try:
                raw = float(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            values.append(raw / 1000.0 if raw > 1000.0 else raw)
    return round(max(values), 3) if values else None


def sample_board_resources() -> dict[str, Any]:
    snapshot = _read_meminfo()
    snapshot["temperature_c"] = _read_temperature_c()
    snapshot["sampled_monotonic_sec"] = round(time.monotonic(), 3)
    return snapshot


class ResourceGate:
    def __init__(
        self,
        config: dict[str, Any] | None,
        sampler: Callable[[], dict[str, Any]] = sample_board_resources,
    ) -> None:
        self.config = config or {}
        self.sampler = sampler
        status = str(self.config.get("status") or "disabled")
        self.enabled = status.startswith("enabled")
        self.fail_closed_on_missing_metrics = bool(self.config.get("fail_closed_on_missing_metrics", True))
        self.reject_count = 0
        self.pass_count = 0

    def evaluate(
        self,
        worker: str,
        queue_depth: int,
        detector_fps: float | None = None,
        detector_alive: bool | None = None,
    ) -> dict[str, Any]:
        snapshot = self.sampler()
        snapshot["event_queue_depth"] = int(queue_depth)
        snapshot["detector_fps_current"] = round(detector_fps, 6) if detector_fps is not None else None
        snapshot["detector_alive"] = detector_alive
        reasons: list[str] = []
        if self.enabled:
            checks = (
                ("available_ram_mb", "min_available_ram_mb", "below_minimum"),
                ("swap_used_mb", "max_swap_used_mb", "above_maximum"),
                ("temperature_c", "max_temperature_c", "above_maximum"),
            )
            for metric, threshold_key, relation in checks:
                threshold = self.config.get(f"{threshold_key}_for_{worker}", self.config.get(threshold_key))
                if threshold is None:
                    continue
                value = snapshot.get(metric)
                if value is None:
                    if self.fail_closed_on_missing_metrics:
                        reasons.append(f"missing_{metric}")
                    continue
                if relation == "below_minimum" and float(value) < float(threshold):
                    reasons.append(f"{metric}_below_{threshold}")
                if relation == "above_maximum" and float(value) > float(threshold):
                    reasons.append(f"{metric}_above_{threshold}")
            queue_limit = self.config.get(f"max_event_queue_depth_for_{worker}")
            if queue_limit is not None and int(queue_depth) > int(queue_limit):
                reasons.append(f"event_queue_depth_above_{queue_limit}")
            fps_floor = self.config.get("detector_fps_floor")
            if fps_floor is not None and detector_alive is not None:
                if detector_fps is None:
                    if self.fail_closed_on_missing_metrics:
                        reasons.append("missing_detector_fps_current")
                elif float(detector_fps) < float(fps_floor):
                    reasons.append(f"detector_fps_below_{fps_floor}")
            if detector_alive is False:
                reasons.append("detector_not_alive")
        allowed = not reasons
        if allowed:
            self.pass_count += 1
        else:
            self.reject_count += 1
        return {
            "enabled": self.enabled,
            "worker": worker,
            "allowed": allowed,
            "reasons": reasons,
            "snapshot": snapshot,
            "policy_status": self.config.get("status", "disabled"),
        }
