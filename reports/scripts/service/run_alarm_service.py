#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "run_demo"
BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"
SERVICE_DIR = Path(__file__).resolve().parent
for candidate in (SCRIPT_DIR, BENCHMARK_DIR, SERVICE_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from alarm_sink import JsonlWriter  # noqa: E402
from asset_worker import FrameCacheAssetWorker, NullAssetWorker, SourceMediaAssetWorker  # noqa: E402
from build_alarm_json import build_alarm  # noqa: E402
from common import parse_simple_yaml, utc_now_iso  # noqa: E402
from detector_service import (  # noqa: E402
    TAIL_PARTIAL_LINE_GUARD_VERSION,
    EventPackageReplayService,
    ReplayDetectorService,
    ResidentProcessDetectorService,
)
from event_queue import BoundedEventQueue  # noqa: E402
from run_alarm_stability_window import read_monitor_peaks  # noqa: E402
from run_alarm_system_benchmark import build_raw_row  # noqa: E402
from text_worker import ServiceTextWorker  # noqa: E402
from vlm_worker import ServiceVlmWorker  # noqa: E402


def log_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{utc_now_iso()} {message}\n")


def default_paths(board: str, run_id: str) -> dict[str, Path]:
    raw_root = Path("benchmark/raw/05_alarm_system") / board
    return {
        "events": raw_root / "events" / f"{run_id}_events.jsonl",
        "llm": raw_root / f"{run_id}_llm_outputs.jsonl",
        "vlm": raw_root / f"{run_id}_vlm_outputs.jsonl",
        "alarms": raw_root / "alarms" / f"{run_id}_alarms.jsonl",
        "benchmark": raw_root / f"{run_id}_alarm_system_benchmark.jsonl",
        "stability": raw_root / f"{run_id}_alarm_system_stability.jsonl",
        "service_log": Path("logs/runtime/05_alarm_system") / board / f"{run_id}_service.log",
    }


def same_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def forbidden_project_path_markers() -> tuple[str, ...]:
    project3 = "/".join(["projects", "03_video_pipeline"])
    project4 = "/".join(["projects", "04_llm_vlm_independent"])
    return (
        project3,
        project3.replace("/", "\\"),
        project4,
        project4.replace("/", "\\"),
    )


def split_detector_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=(os.name != "nt"))
    if not parts:
        raise SystemExit("--detector-command is empty")
    normalized = command.replace("\\", "/")
    forbidden = [marker.replace("\\", "/") for marker in forbidden_project_path_markers()]
    if any(marker in normalized for marker in forbidden):
        raise SystemExit(
            "--detector-command must point to a Project 05 local detector binary or wrapper, "
            "not a legacy cross-project runtime."
        )
    return parts


def resolve_llama_server_bin(llama_server_bin: str, llama_bin: str) -> Path:
    if llama_server_bin:
        return Path(llama_server_bin)
    if llama_bin:
        llama_cli = Path(llama_bin)
        sibling_names = ["llama-server.exe", "llama-server"] if os.name == "nt" else ["llama-server"]
        for sibling_name in sibling_names:
            sibling = llama_cli.with_name(sibling_name)
            if sibling.exists():
                return sibling
    which = shutil.which("llama-server")
    if which:
        return Path(which)
    return Path("llama-server")


def resolve_llama_server_bin_arg(args: argparse.Namespace) -> Path:
    return resolve_llama_server_bin(getattr(args, "llama_server_bin", ""), getattr(args, "llama_bin", ""))


def resolve_vlm_llama_server_bin_arg(args: argparse.Namespace) -> Path:
    return resolve_llama_server_bin(
        getattr(args, "vlm_llama_server_bin", "") or getattr(args, "llama_server_bin", ""),
        getattr(args, "llama_bin", ""),
    )


def build_stability_row(
    args: argparse.Namespace,
    combo: dict[str, Any],
    detector: Any,
    queue: BoundedEventQueue,
    llm_calls: int,
    vlm_calls: int,
    alarm_count: int,
    processed_records: list[dict[str, Any]],
    started: float,
    service_log: Path,
) -> dict[str, Any]:
    monitor = read_monitor_peaks(args.monitor_log)
    actual_window_sec = round(time.monotonic() - started, 3)
    requested_window_sec = float(args.window_sec) if args.window_sec > 0 else None
    window_requirement_met = (
        requested_window_sec is None or actual_window_sec >= requested_window_sec
    )
    duration_failure = (
        getattr(args, "source_mode", "") == "resident_process"
        and requested_window_sec is not None
        and not window_requirement_met
    )
    event_domain_counts = Counter()
    event_type_counts = Counter()
    for event in detector.generated_events:
        event_domain_counts[event.get("alarm_domain", "visual_detection")] += 1
        event_type_counts[event.get("alarm_type", "generic_object_event")] += 1
    fallback_domain_counts = Counter()
    fallback_count = 0
    for record in processed_records:
        event = record["event"]
        llm_row = record["llm_row"]
        vlm_row = record["vlm_row"]
        llm_fallback = llm_row.get("status") in {"stub", "fallback", "not_executed"}
        vlm_fallback = vlm_row.get("status") in {"stub", "fallback", "not_executed"}
        if llm_fallback or vlm_fallback:
            fallback_count += 1
            fallback_domain_counts[event.get("alarm_domain", "visual_detection")] += 1
    return {
        "run_id": args.run_id,
        "timestamp": utc_now_iso(),
        "schema_version": 1,
        "project": "05_alarm_system",
        "measurement_granularity": "time_window",
        "board": args.board_name,
        "target": args.board,
        "environment_baseline_id": args.environment_baseline_id,
        "model_combo_id": combo.get("model_combo_id", "unknown_combo"),
        "input_source_id": args.input_source_id,
        "stability_tier": args.stability_tier,
        "window_index": 0,
        "window_sec": actual_window_sec,
        "requested_window_sec": requested_window_sec,
        "window_requirement_met": window_requirement_met,
        "detection_fps": (
            round(detector.frame_count / actual_window_sec, 6)
            if actual_window_sec and detector.frame_count
            else None
        ),
        "event_count": detector.event_count,
        "event_count_by_alarm_domain": dict(event_domain_counts),
        "event_count_by_alarm_type": dict(event_type_counts),
        "alarm_count": alarm_count,
        "vlm_call_count": vlm_calls,
        "llm_call_count": llm_calls,
        "event_queue_depth": queue.stats.max_depth,
        "drop_count": queue.stats.dropped,
        "end_to_end_alarm_ms": None,
        "memory_mb": monitor["memory_mb"],
        "swap_used_mb": monitor["swap_used_mb"],
        "temperature_c": monitor["temperature_c"],
        "power_w": monitor["power_w"],
        "fallback_count": fallback_count,
        "fallback_count_by_alarm_domain": dict(fallback_domain_counts),
        "error_count": 0,
        "restart_count": int(getattr(detector, "restart_count", 0)),
        "reconnect_count": 0,
        "service_status": "failed" if duration_failure else args.service_status,
        "status": "fail" if duration_failure else args.status,
        "runtime_log_path": str(service_log),
        "monitor_log_path": str(args.monitor_log) if args.monitor_log else None,
        "failure_log_path": None,
        "related_troubleshooting_id": (
            None if getattr(args, "source_mode", "") == "resident_process" else "P05-RESIDENT-SERVICE-REPLAY-001"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project 05 alarm service with resident detector process, replay, or event input.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--board", required=True, choices=["jetson_8gb", "rk3588_8gb", "pc"])
    parser.add_argument("--board-name", default="")
    parser.add_argument("--environment-baseline-id", required=True)
    parser.add_argument(
        "--detector-mode",
        choices=["auto", "resident_process", "replay", "events_input"],
        default="auto",
        help="auto infers from --events-input, --detector-command, or --detector-raw.",
    )
    parser.add_argument("--detector-command", default="", help="Project 05 local detector command to run as a resident process.")
    parser.add_argument("--detector-output", type=Path, default=None, help="JSONL file written by the resident detector process.")
    parser.add_argument("--detector-runtime-log", type=Path, default=None)
    parser.add_argument("--detector-startup-timeout-sec", type=float, default=10.0)
    parser.add_argument("--detector-poll-interval-sec", type=float, default=0.2)
    parser.add_argument("--detector-start-retries", type=int, default=0)
    parser.add_argument("--detector-restart-delay-sec", type=float, default=3.0)
    parser.add_argument("--detector-start-order", choices=["early", "after_workers"], default="early")
    parser.add_argument("--detector-raw", type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--events-input", type=Path, default=None)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--input-source-id", default="video_set_runtime_v1")
    parser.add_argument("--queue-capacity", type=int, default=16)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--min-frame-gap", type=int, default=30)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--stability-tier", choices=["smoke", "required", "target", "stress"], default="smoke")
    parser.add_argument("--window-sec", type=float, default=0.0)
    parser.add_argument("--status", choices=["pass", "fail", "degraded", "blocked", "not_executed", "not_verified"], default="not_verified")
    parser.add_argument("--service-status", choices=["running", "degraded", "restarting", "stopped", "failed", "unknown"], default="stopped")
    parser.add_argument("--monitor-log", type=Path, default=None)
    parser.add_argument("--asset-mode", choices=["none", "source_media"], default="none")
    parser.add_argument("--asset-source-type", choices=["video_file", "video_playlist", "frame_cache_dir"], default="")
    parser.add_argument("--asset-source-uri", type=Path, default=None)
    parser.add_argument("--asset-dir", type=Path, default=None)
    parser.add_argument("--asset-trigger-policy", choices=["all_events", "vlm_real_calls_only"], default="all_events")
    parser.add_argument("--asset-image-ext", choices=["jpg", "png"], default="jpg")
    parser.add_argument("--asset-jpeg-quality", type=int, default=92)
    parser.add_argument("--asset-playlist-loop", action="store_true")
    parser.add_argument("--text-mode", choices=["template", "llama_cpp", "llama_cpp_resident", "rkllm", "rkllm_resident"], default="template")
    parser.add_argument("--text-model-path", default="")
    parser.add_argument("--llama-bin", default="llama-cli")
    parser.add_argument("--llama-server-bin", default="")
    parser.add_argument("--llama-server-host", default="127.0.0.1")
    parser.add_argument("--llama-server-port", type=int, default=0)
    parser.add_argument("--llama-server-no-jinja", action="store_true")
    parser.add_argument("--text-no-kv-offload", action="store_true")
    parser.add_argument("--text-device", default="")
    parser.add_argument("--text-ctx", type=int, default=512)
    parser.add_argument("--text-max-tokens", type=int, default=128)
    parser.add_argument("--text-temperature", type=float, default=0.0)
    parser.add_argument("--text-timeout-ms", type=int, default=10000)
    parser.add_argument("--text-startup-timeout-ms", type=int, default=30000)
    parser.add_argument("--text-max-calls", type=int, default=-1, help="-1 means no service-level text call limit.")
    parser.add_argument("--ngl", type=int, default=None)
    parser.add_argument("--qwen-no-think", action="store_true")
    parser.add_argument("--capture-mode", choices=["auto", "script", "pty", "subprocess"], default="auto")
    parser.add_argument("--session-log-dir", type=Path, default=None)
    parser.add_argument("--extra-arg", action="append", default=[])
    parser.add_argument(
        "--rkllm-wrapper",
        type=Path,
        default=Path("projects/05_alarm_system/scripts/service/runtime_adapters/run_rkllm_single_turn.sh"),
    )
    parser.add_argument("--rkllm-runner", type=Path, default=None)
    parser.add_argument("--text-metrics-dir", type=Path, default=None)
    parser.add_argument("--text-runtime-log-dir", type=Path, default=None)
    parser.add_argument("--rkllm-taskset-mask", default="")
    parser.add_argument(
        "--vlm-mode",
        choices=[
            "stub",
            "rkllm_multimodal",
            "rkllm_multimodal_resident",
            "llama_cpp_multimodal_once",
            "llama_cpp_multimodal_resident",
        ],
        default="stub",
    )
    parser.add_argument(
        "--rkllm-mm-wrapper",
        type=Path,
        default=Path("projects/05_alarm_system/scripts/service/runtime_adapters/run_rkllm_multimodal_once.sh"),
    )
    parser.add_argument(
        "--rkllm-mm-runner",
        type=Path,
        default=Path("projects/05_alarm_system/runners/rkllm_multimodal_once/build/rkllm_multimodal_once"),
    )
    parser.add_argument("--rkllm-mm-resident-runner", type=Path, default=None)
    parser.add_argument("--vlm-model-path", default="")
    parser.add_argument("--mmproj-path", default="")
    parser.add_argument("--vlm-llama-server-bin", default="")
    parser.add_argument("--vlm-llama-server-host", default="127.0.0.1")
    parser.add_argument("--vlm-llama-server-port", type=int, default=0)
    parser.add_argument("--vlm-llama-server-no-jinja", action="store_true")
    parser.add_argument("--vlm-no-kv-offload", action="store_true")
    parser.add_argument("--vlm-device", default="")
    parser.add_argument("--vision-model", type=Path, default=None)
    parser.add_argument("--decoder-model", type=Path, default=None)
    parser.add_argument("--vlm-metrics-dir", type=Path, default=None)
    parser.add_argument("--vlm-runtime-log-dir", type=Path, default=None)
    parser.add_argument("--vlm-ctx", type=int, default=2048)
    parser.add_argument("--vlm-max-tokens", type=int, default=128)
    parser.add_argument("--vlm-temperature", type=float, default=0.0)
    parser.add_argument("--vlm-timeout-ms", type=int, default=45000)
    parser.add_argument("--vlm-startup-timeout-ms", type=int, default=30000)
    parser.add_argument("--vlm-max-calls", type=int, default=-1, help="-1 means no service-level VLM call limit.")
    parser.add_argument("--vlm-request-retries", type=int, default=0)
    parser.add_argument("--vlm-ngl", type=int, default=None)
    parser.add_argument("--vlm-image-min-tokens", type=int, default=1024)
    parser.add_argument("--vlm-image-max-tokens", type=int, default=1024)
    parser.add_argument("--vlm-no-mmproj-offload", action="store_true")
    parser.add_argument("--npu-core-num", type=int, default=3)
    parser.add_argument("--vlm-img-start", default="<|vision_start|>")
    parser.add_argument("--vlm-img-end", default="<|vision_end|>")
    parser.add_argument("--vlm-img-content", default="<|image_pad|>")
    parser.add_argument("--vlm-template-style", default="qwen")
    args = parser.parse_args()

    if args.detector_mode == "auto":
        if args.events_input:
            args.detector_mode = "events_input"
        elif args.detector_command:
            args.detector_mode = "resident_process"
        elif args.detector_raw:
            args.detector_mode = "replay"
        else:
            raise SystemExit("one input mode is required: --detector-command, --detector-raw, or --events-input")

    if args.detector_mode == "events_input":
        if not args.events_input:
            raise SystemExit("--events-input is required when --detector-mode=events_input")
        if not args.events_input.exists():
            raise SystemExit(f"--events-input not found: {args.events_input}")
        source_mode = "events_input"
    elif args.detector_mode == "resident_process":
        if not args.detector_command:
            raise SystemExit("--detector-command is required when --detector-mode=resident_process")
        if not args.detector_output:
            raise SystemExit("--detector-output is required when --detector-mode=resident_process")
        if not args.rules:
            raise SystemExit("--rules is required when --detector-mode=resident_process")
        if not args.rules.exists():
            raise SystemExit(f"--rules not found: {args.rules}")
        args.detector_command_parts = split_detector_command(args.detector_command)
        source_mode = "resident_process"
    elif args.detector_mode == "replay":
        if not args.detector_raw:
            raise SystemExit("--detector-raw is required when --detector-mode=replay")
        if not args.rules:
            raise SystemExit("--rules is required when --detector-mode=replay")
        if not args.detector_raw.exists():
            raise SystemExit(f"--detector-raw not found: {args.detector_raw}")
        if not args.rules.exists():
            raise SystemExit(f"--rules not found: {args.rules}")
        source_mode = "detector_replay"
    else:
        raise SystemExit(f"unsupported detector mode: {args.detector_mode}")
    args.source_mode = source_mode

    text_real_calls_enabled = args.text_mode in {"llama_cpp", "llama_cpp_resident", "rkllm", "rkllm_resident"} and args.text_max_calls != 0
    vlm_real_calls_enabled = args.vlm_mode in {
        "rkllm_multimodal",
        "rkllm_multimodal_resident",
        "llama_cpp_multimodal_once",
        "llama_cpp_multimodal_resident",
    } and args.vlm_max_calls != 0
    if text_real_calls_enabled and not args.text_model_path:
        raise SystemExit("--text-model-path is required when --text-mode is llama_cpp, llama_cpp_resident, rkllm, or rkllm_resident")
    if text_real_calls_enabled and not Path(args.text_model_path).exists():
        raise SystemExit(f"--text-model-path not found: {args.text_model_path}")
    if text_real_calls_enabled and args.text_mode == "llama_cpp_resident":
        llama_server_bin = resolve_llama_server_bin_arg(args)
        if not llama_server_bin.exists():
            raise SystemExit(f"resolved llama-server binary not found: {llama_server_bin}")
    if text_real_calls_enabled and args.text_mode == "rkllm" and not args.rkllm_wrapper.exists():
        raise SystemExit(f"--rkllm-wrapper not found: {args.rkllm_wrapper}")
    if text_real_calls_enabled and args.text_mode == "rkllm" and args.rkllm_runner and not args.rkllm_runner.exists():
        raise SystemExit(f"--rkllm-runner not found: {args.rkllm_runner}")
    if text_real_calls_enabled and args.text_mode == "rkllm_resident" and args.rkllm_runner and not args.rkllm_runner.exists():
        raise SystemExit(f"--rkllm-runner not found: {args.rkllm_runner}")
    if vlm_real_calls_enabled and args.vlm_mode == "rkllm_multimodal":
        missing = []
        for label, path in [
            ("--rkllm-mm-wrapper", args.rkllm_mm_wrapper),
            ("--rkllm-mm-runner", args.rkllm_mm_runner),
            ("--vision-model", args.vision_model),
            ("--decoder-model", args.decoder_model),
        ]:
            if path is None or not Path(path).exists():
                missing.append(f"{label}={path}")
        if missing:
            raise SystemExit("missing required VLM artifact(s): " + ", ".join(missing))
    if vlm_real_calls_enabled and args.vlm_mode == "rkllm_multimodal_resident":
        missing = []
        for label, path in [
            ("--vision-model", args.vision_model),
            ("--decoder-model", args.decoder_model),
        ]:
            if path is None or not Path(path).exists():
                missing.append(f"{label}={path}")
        if args.rkllm_mm_resident_runner is not None and not args.rkllm_mm_resident_runner.exists():
            missing.append(f"--rkllm-mm-resident-runner={args.rkllm_mm_resident_runner}")
        if missing:
            raise SystemExit("missing required resident VLM artifact(s): " + ", ".join(missing))
    if vlm_real_calls_enabled and args.vlm_mode in {"llama_cpp_multimodal_once", "llama_cpp_multimodal_resident"}:
        missing = []
        if not args.vlm_model_path:
            missing.append("--vlm-model-path=")
        elif not Path(args.vlm_model_path).exists():
            missing.append(f"--vlm-model-path={args.vlm_model_path}")
        if not args.mmproj_path:
            missing.append("--mmproj-path=")
        elif not Path(args.mmproj_path).exists():
            missing.append(f"--mmproj-path={args.mmproj_path}")
        llama_server_bin = resolve_vlm_llama_server_bin_arg(args)
        if not llama_server_bin.exists():
            missing.append(f"resolved_vlm_llama_server_bin={llama_server_bin}")
        if missing:
            raise SystemExit("missing required llama.cpp resident VLM artifact(s): " + ", ".join(missing))
    if args.asset_mode == "source_media":
        if not args.asset_source_type:
            raise SystemExit("--asset-source-type is required when --asset-mode=source_media")
        if args.asset_source_uri is None:
            raise SystemExit("--asset-source-uri is required when --asset-mode=source_media")
        if args.asset_dir is None:
            raise SystemExit("--asset-dir is required when --asset-mode=source_media")

    args.board_name = args.board_name or {"jetson_8gb": "Jetson 8GB", "rk3588_8gb": "RK3588 8GB", "pc": "PC"}[args.board]
    paths = default_paths(args.board, args.run_id)
    if args.detector_mode == "events_input" and same_path(args.events_input, paths["events"]):
        raise SystemExit(
            "--events-input points to the same path as the current run output events file. "
            "Use a different RUN_ID for outputs, or keep the source event file under a different name."
        )
    for path in paths.values():
        if path.exists() and path.is_file():
            path.unlink()

    combo = parse_simple_yaml(args.model_config)
    queue = BoundedEventQueue(args.queue_capacity)
    if args.detector_mode == "events_input":
        detector = EventPackageReplayService(args.events_input, args.run_id, max_events=args.max_events)
    elif args.detector_mode == "resident_process":
        detector = ResidentProcessDetectorService(
            args.detector_command_parts,
            args.detector_output,
            args.rules,
            args.run_id,
            max_frames=args.max_frames,
            max_events=args.max_events,
            min_frame_gap=args.min_frame_gap,
            fps=args.fps,
            startup_timeout_sec=args.detector_startup_timeout_sec,
            poll_interval_sec=args.detector_poll_interval_sec,
            runtime_log=args.detector_runtime_log,
            max_start_retries=args.detector_start_retries,
            restart_delay_sec=args.detector_restart_delay_sec,
        )
    else:
        detector = ReplayDetectorService(
            args.detector_raw,
            args.rules,
            args.run_id,
            max_frames=args.max_frames,
            max_events=args.max_events,
            min_frame_gap=args.min_frame_gap,
            fps=args.fps,
        )
    detector.generated_events = []  # type: ignore[attr-defined]
    if args.asset_mode == "source_media":
        if args.asset_source_type == "frame_cache_dir":
            asset_worker = FrameCacheAssetWorker(
                source_uri=args.asset_source_uri,
                asset_dir=args.asset_dir,
                image_ext=args.asset_image_ext,
                jpeg_quality=args.asset_jpeg_quality,
            )
        else:
            asset_worker = SourceMediaAssetWorker(
                source_type=args.asset_source_type,
                source_uri=args.asset_source_uri,
                asset_dir=args.asset_dir,
                image_ext=args.asset_image_ext,
                jpeg_quality=args.asset_jpeg_quality,
                playlist_loop=args.asset_playlist_loop,
            )
    else:
        asset_worker = NullAssetWorker()
    detector_started_early = False
    text_worker = None
    vlm_worker = None
    try:
        if (
            args.detector_mode == "resident_process"
            and args.detector_start_order == "early"
            and hasattr(detector, "start")
        ):
            detector.start()
            detector_started_early = True
        text_worker = ServiceTextWorker(args.text_mode, combo, args, paths["llm"])
        vlm_worker = ServiceVlmWorker(args.vlm_mode, combo.get("image_vlm", {}), args, paths["vlm"])
    except Exception:
        asset_worker.close()
        if detector_started_early and hasattr(detector, "close"):
            detector.close()
        raise

    event_writer = JsonlWriter(paths["events"])
    llm_writer = JsonlWriter(paths["llm"])
    vlm_writer = JsonlWriter(paths["vlm"])
    alarm_writer = JsonlWriter(paths["alarms"])
    benchmark_writer = JsonlWriter(paths["benchmark"])
    stability_writer = JsonlWriter(paths["stability"])
    started = time.monotonic()
    processed_records: list[dict[str, Any]] = []
    log_line(
        paths["service_log"],
        (
            f"service_start run_id={args.run_id} board={args.board} source_mode={source_mode} "
            f"text_mode={args.text_mode} vlm_mode={args.vlm_mode} detector_mode={args.detector_mode} "
            f"detector_start_order={args.detector_start_order} tail_guard={TAIL_PARTIAL_LINE_GUARD_VERSION}"
        ),
    )
    text_runtime_info = text_worker.runtime_info()
    vlm_runtime_info = vlm_worker.runtime_info()
    log_line(
        paths["service_log"],
        "asset_worker_info "
        + " ".join(f"{key}={value}" for key, value in asset_worker.runtime_info().items() if value is not None),
    )
    log_line(
        paths["service_log"],
        "text_worker_info "
        + " ".join(f"{key}={value}" for key, value in text_runtime_info.items() if value is not None),
    )
    log_line(
        paths["service_log"],
        "vlm_worker_info "
        + " ".join(f"{key}={value}" for key, value in vlm_runtime_info.items() if value is not None),
    )
    print(f"tail_guard={TAIL_PARTIAL_LINE_GUARD_VERSION}")
    asset_skipped_events = 0
    vlm_asset_reservations = 0

    def should_prepare_assets_before_queue() -> bool:
        nonlocal vlm_asset_reservations
        if args.asset_mode != "source_media":
            return False
        if args.asset_trigger_policy == "all_events":
            return True
        if not vlm_real_calls_enabled:
            return False
        if args.vlm_max_calls < 0:
            vlm_asset_reservations += 1
            return True
        if vlm_asset_reservations >= args.vlm_max_calls:
            return False
        vlm_asset_reservations += 1
        return True

    def worker_loop() -> None:
        nonlocal asset_skipped_events
        while True:
            event = queue.get()
            if event is None:
                queue.task_done()
                return
            asset_prepared = bool(event.pop("__asset_prepared", False))
            if args.asset_mode == "source_media":
                should_prepare_assets = args.asset_trigger_policy == "all_events" or vlm_worker.should_prepare_assets()
                if should_prepare_assets:
                    if not asset_prepared:
                        event = asset_worker.enrich(event)
                else:
                    asset_skipped_events += 1
            timestamp = utc_now_iso()
            llm_row = text_worker.explain(event, timestamp)
            vlm_row = vlm_worker.review(event, timestamp)
            alarm = build_alarm(
                event,
                combo,
                {event["event_id"]: llm_row},
                {event["event_id"]: vlm_row},
                {},
                str(paths["benchmark"]),
            )
            alarm["evidence"]["event_package_path"] = str(paths["events"])
            raw_row = build_raw_row(
                event,
                alarm,
                combo,
                args.board,
                args.environment_baseline_id,
                paths["events"],
                paths["alarms"],
            )
            raw_row["status"] = args.status
            raw_row["monitor_log_path"] = str(args.monitor_log) if args.monitor_log else raw_row.get("monitor_log_path")
            event_writer.write(event)
            llm_writer.write(llm_row)
            vlm_writer.write(vlm_row)
            alarm_writer.write(alarm)
            benchmark_writer.write(raw_row)
            processed_records.append({"event": event, "llm_row": llm_row, "vlm_row": vlm_row})
            queue.task_done()

    worker = threading.Thread(target=worker_loop, name="alarm-worker", daemon=True)
    worker.start()
    for event in detector.iter_events(queue.depth):
        if should_prepare_assets_before_queue():
            event = asset_worker.enrich(event)
            event["__asset_prepared"] = True
        detector.generated_events.append(event)  # type: ignore[attr-defined]
        if not queue.put_event(event):
            log_line(paths["service_log"], f"event_drop event_id={event.get('event_id')} policy={queue.drop_policy}")
    queue.stop()
    worker.join()
    asset_worker.close()
    text_worker.close()
    if hasattr(vlm_worker, "close"):
        vlm_worker.close()

    stability_row = build_stability_row(
        args,
        combo,
        detector,
        queue,
        text_worker.call_count,
        vlm_worker.call_count,
        alarm_writer.count,
        processed_records,
        started,
        paths["service_log"],
    )
    stability_writer.write(stability_row)
    for writer in (event_writer, llm_writer, vlm_writer, alarm_writer, benchmark_writer, stability_writer):
        writer.close()
    log_line(
        paths["service_log"],
        (
            f"service_stop frames={detector.frame_count} events={detector.event_count} "
            f"alarms={alarm_writer.count} queue_dropped={queue.stats.dropped} "
            f"asset_events={asset_worker.stats.processed_events} "
            f"asset_skipped={asset_skipped_events} "
            f"asset_success={asset_worker.stats.success_events} "
            f"asset_degraded={asset_worker.stats.degraded_events} "
            f"asset_keyframes={asset_worker.stats.keyframes_written} "
            f"asset_rois={asset_worker.stats.roi_images_written}"
        ),
    )
    duration_failure = (
        getattr(args, "source_mode", "") == "resident_process"
        and stability_row["requested_window_sec"] is not None
        and not stability_row["window_requirement_met"]
    )
    if duration_failure:
        log_line(
            paths["service_log"],
            (
                "duration_requirement_failed "
                f"actual_window_sec={stability_row['window_sec']} "
                f"requested_window_sec={stability_row['requested_window_sec']}"
            ),
        )
    print(f"service_status={stability_row['service_status']}")
    print(f"status={stability_row['status']}")
    print(
        "window_sec="
        f"{stability_row['window_sec']} "
        f"requested_window_sec={stability_row['requested_window_sec']} "
        f"window_requirement_met={stability_row['window_requirement_met']}"
    )
    print(f"events={event_writer.count} alarms={alarm_writer.count} benchmark_rows={benchmark_writer.count}")
    for key in ("events", "llm", "vlm", "alarms", "benchmark", "stability", "service_log"):
        print(f"{key}={paths[key]}")
    return 2 if duration_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
