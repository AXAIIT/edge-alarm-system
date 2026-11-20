#!/usr/bin/env python3
from __future__ import annotations

import sys
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_event_trigger import EventRuleStateMachine, load_rule_config  # noqa: E402

TAIL_PARTIAL_LINE_GUARD_VERSION = "p05_tail_guard_v2"


def normalize_event_route(event: dict[str, Any]) -> dict[str, Any]:
    updated = dict(event)
    alarm_type = str(updated.get("alarm_type") or "generic_object_event")
    if not updated.get("route_target"):
        if alarm_type in {"person_presence", "vehicle_presence", "generic_object_event"}:
            route_target = "rule_only"
        elif alarm_type in {"multi_object_scene", "visual_abnormal_review", "device_panel_state_review"}:
            route_target = "vlm_then_text"
        elif alarm_type == "roi_object_review":
            route_target = "vlm_only"
        elif alarm_type in {"alarm_reasoning", "detection_json_summary", "pipeline_runtime_fault", "model_runtime_fault"}:
            route_target = "text_only"
        else:
            route_target = "template_only"
        updated["route_target"] = route_target
        updated["route_reason"] = "legacy_event_route_inferred_by_alarm_type"
    route_target = str(updated["route_target"])
    updated.setdefault("alarm_revision", 0)
    updated["needs_text"] = route_target in {"text_only", "text_then_vlm", "vlm_then_text"}
    updated["needs_vlm"] = route_target in {"vlm_only", "text_then_vlm", "vlm_then_text"}
    if route_target in {"text_then_vlm", "vlm_then_text"} and alarm_type == "multi_object_scene":
        updated.setdefault("vlm_purpose", "relationship_review")
        updated.setdefault("text_purpose", "detector_fact_alarm_explanation"
                           if route_target == "text_then_vlm" else "post_vlm_alarm_explanation")
    else:
        updated.setdefault("vlm_purpose", None)
        updated.setdefault("text_purpose", "alarm_explanation" if route_target == "text_only" else None)
    if not updated.get("evidence_hash"):
        payload = {
            "event_id": updated.get("event_id"),
            "frame_id": updated.get("frame_id"),
            "detections": updated.get("detections") or [],
        }
        updated["evidence_hash"] = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return updated


class DetectorRuleEngine:
    def __init__(
        self,
        rules_path: Path,
        run_id: str,
        max_frames: int = 0,
        max_events: int = 0,
        min_frame_gap: int = 30,
        fps: float = 30.0,
    ) -> None:
        self.ruleset = load_rule_config(rules_path)
        self.run_id = run_id
        self.max_frames = max_frames
        self.max_events = max_events
        self.min_frame_gap = min_frame_gap
        self.fps = fps
        self.frame_count = 0
        self.event_count = 0
        self.rule_state_machine = EventRuleStateMachine(self.ruleset, run_id, fps)

    def _iter_events_from_rows(
        self,
        rows: Iterator[tuple[int, dict[str, Any]]],
        queue_depth_fn,
    ) -> Iterator[dict[str, Any]]:
        for _, row in rows:
            self.frame_count += 1
            for event in self.rule_state_machine.process(row, self.event_count):
                event["queue_depth_at_trigger"] = int(queue_depth_fn())
                event["queue_metrics"]["drop_policy"] = "drop_newest"
                self.event_count += 1
                yield event
            if self.max_frames and self.frame_count >= self.max_frames:
                return
            if self.max_events and self.event_count >= self.max_events:
                return

    def _parse_jsonl_row(self, source: Path, line_no: int, line: str) -> dict[str, Any]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{source}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"{source}:{line_no}: expected object row")
        return row

class ReplayDetectorService(DetectorRuleEngine):
    def __init__(
        self,
        detector_raw: Path,
        rules_path: Path,
        run_id: str,
        max_frames: int = 0,
        max_events: int = 0,
        min_frame_gap: int = 30,
        fps: float = 30.0,
    ) -> None:
        super().__init__(rules_path, run_id, max_frames, max_events, min_frame_gap, fps)
        self.detector_raw = detector_raw

    def iter_events(self, queue_depth_fn) -> Iterator[dict[str, Any]]:
        yield from self._iter_events_from_rows(self._iter_rows(), queue_depth_fn)

    def _iter_rows(self) -> Iterator[tuple[int, dict[str, Any]]]:
        with self.detector_raw.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                yield line_no, self._parse_jsonl_row(self.detector_raw, line_no, line)


class ResidentProcessDetectorService(DetectorRuleEngine):
    def __init__(
        self,
        command: list[str],
        detector_output: Path,
        rules_path: Path,
        run_id: str,
        max_frames: int = 0,
        max_events: int = 0,
        min_frame_gap: int = 30,
        fps: float = 30.0,
        startup_timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.2,
        runtime_log: Path | None = None,
        max_start_retries: int = 0,
        restart_delay_sec: float = 3.0,
    ) -> None:
        super().__init__(rules_path, run_id, max_frames, max_events, min_frame_gap, fps)
        self.command = command
        self.detector_output = detector_output
        self.startup_timeout_sec = startup_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.runtime_log = runtime_log
        self.max_start_retries = max(0, int(max_start_retries))
        self.restart_delay_sec = max(0.0, float(restart_delay_sec))
        self.process: subprocess.Popen[str] | None = None
        self.log_handle = None
        self._started = False
        self.restart_count = 0

    def iter_events(self, queue_depth_fn) -> Iterator[dict[str, Any]]:
        yield from self._iter_events_from_rows(self._iter_rows_from_process(), queue_depth_fn)

    def start(self) -> None:
        if self._started:
            return
        self.detector_output.parent.mkdir(parents=True, exist_ok=True)
        if self.detector_output.exists():
            self.detector_output.unlink()
        if self.runtime_log and self.log_handle is None:
            self.runtime_log.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = self.runtime_log.open("a", encoding="utf-8")
        attempt = 0
        while True:
            self._launch_process()
            try:
                self._wait_for_output()
                self._started = True
                return
            except SystemExit as exc:
                if not self._can_retry_start(exc, attempt):
                    raise
                attempt += 1
                self.restart_count += 1
                self._log_restart(attempt, str(exc))
                self._stop_process()
                if self.detector_output.exists():
                    self.detector_output.unlink()
                if self.restart_delay_sec > 0:
                    time.sleep(self.restart_delay_sec)

    def close(self) -> None:
        self._stop_process()
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self._started = False

    def _iter_rows_from_process(self) -> Iterator[tuple[int, dict[str, Any]]]:
        try:
            self.start()
            yield from self._tail_detector_output()
            return_code = self.process.wait(timeout=5)
            if return_code != 0:
                raise SystemExit(f"resident detector exited with non-zero code: {return_code}")
        finally:
            self.close()

    def _wait_for_output(self) -> None:
        deadline = time.monotonic() + self.startup_timeout_sec
        while not self.detector_output.exists():
            if self.process and self.process.poll() is not None:
                raise SystemExit(
                    f"resident detector exited before creating output: {self.detector_output}"
                )
            if time.monotonic() >= deadline:
                raise SystemExit(
                    f"resident detector did not create output within {self.startup_timeout_sec}s: "
                    f"{self.detector_output}"
                )
            time.sleep(self.poll_interval_sec)

    def _launch_process(self) -> None:
        self.process = subprocess.Popen(
            self.command,
            stdout=self.log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def _can_retry_start(self, exc: SystemExit, attempt: int) -> bool:
        if attempt >= self.max_start_retries:
            return False
        message = str(exc)
        return "exited before creating output" in message

    def _log_restart(self, attempt: int, reason: str) -> None:
        if self.log_handle is None:
            return
        self.log_handle.write(
            f"RESIDENT_PROCESS_RESTART: attempt={attempt} "
            f"max_start_retries={self.max_start_retries} "
            f"restart_delay_sec={self.restart_delay_sec} "
            f"reason={reason}\n"
        )
        self.log_handle.flush()

    def _tail_detector_output(self) -> Iterator[tuple[int, dict[str, Any]]]:
        line_no = 0
        with self.detector_output.open("r", encoding="utf-8") as handle:
            while True:
                offset = handle.tell()
                line = handle.readline()
                if line:
                    if not line.endswith("\n"):
                        if self.process and self.process.poll() is None:
                            handle.seek(offset)
                            time.sleep(self.poll_interval_sec)
                            continue
                    line_no += 1
                    line = line.strip()
                    if line:
                        yield line_no, self._parse_jsonl_row(self.detector_output, line_no, line)
                    continue
                if self.process and self.process.poll() is not None:
                    break
                time.sleep(self.poll_interval_sec)

    def _stop_process(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


class EventPackageReplayService:
    def __init__(self, events_input: Path, run_id: str, max_events: int = 0) -> None:
        self.events_input = events_input
        self.run_id = run_id
        self.max_events = max_events
        self.frame_count = 0
        self.event_count = 0

    def iter_events(self, queue_depth_fn) -> Iterator[dict[str, Any]]:
        with self.events_input.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"{self.events_input}:{line_no}: invalid JSON: {exc}") from exc
                if not isinstance(event, dict):
                    raise SystemExit(f"{self.events_input}:{line_no}: expected object row")
                event = normalize_event_route(event)
                event["run_id"] = self.run_id
                event["queue_depth_at_trigger"] = int(queue_depth_fn())
                queue_metrics = event.get("queue_metrics")
                if not isinstance(queue_metrics, dict):
                    queue_metrics = {}
                queue_metrics.setdefault("drop_policy", "drop_newest")
                event["queue_metrics"] = queue_metrics
                self.event_count += 1
                yield event
                if self.max_events and self.event_count >= self.max_events:
                    return
