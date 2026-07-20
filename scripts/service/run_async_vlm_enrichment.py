#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import shutil
import sys
import time
from pathlib import Path
from typing import Any

RUN_DEMO_DIR = Path(__file__).resolve().parents[1] / "run_demo"
BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmark"
SERVICE_DIR = Path(__file__).resolve().parent
for candidate in (RUN_DEMO_DIR, BENCHMARK_DIR, SERVICE_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from alarm_sink import JsonlWriter  # noqa: E402
from asset_worker import FrameCacheAssetWorker, NullAssetWorker, SourceMediaAssetWorker  # noqa: E402
from build_alarm_json import build_alarm  # noqa: E402
from common import index_by_event_id, parse_simple_yaml, read_jsonl, utc_now_iso, write_jsonl  # noqa: E402
from run_alarm_system_benchmark import build_raw_row  # noqa: E402
from vlm_worker import ServiceVlmWorker  # noqa: E402


STOP_REQUESTED = False


def request_stop(signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def log_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now_iso()} {message}\n")


def default_paths(board: str, run_id: str) -> dict[str, Path]:
    raw_root = Path("benchmark/raw/05_alarm_system") / board
    return {
        "vlm": raw_root / f"{run_id}_async_vlm_outputs.jsonl",
        "alarms": raw_root / "alarms" / f"{run_id}_alarm_enriched.jsonl",
        "benchmark": raw_root / f"{run_id}_alarm_enriched_benchmark.jsonl",
        "service_log": Path("logs/runtime/05_alarm_system") / board / f"{run_id}_async_vlm_service.log",
    }


def complete_jsonl_lines(buffer: str) -> tuple[list[str], str]:
    if not buffer:
        return [], ""
    parts = buffer.split("\n")
    if buffer.endswith("\n"):
        return [line for line in parts[:-1] if line.strip()], ""
    return [line for line in parts[:-1] if line.strip()], parts[-1]


def build_asset_worker(args: argparse.Namespace):
    if args.asset_mode != "source_media":
        return NullAssetWorker()
    if args.asset_source_type == "frame_cache_dir":
        return FrameCacheAssetWorker(
            source_uri=args.asset_source_uri,
            asset_dir=args.asset_dir,
            image_ext=args.asset_image_ext,
            jpeg_quality=args.asset_jpeg_quality,
        )
    return SourceMediaAssetWorker(
        source_type=args.asset_source_type,
        source_uri=args.asset_source_uri,
        asset_dir=args.asset_dir,
        image_ext=args.asset_image_ext,
        jpeg_quality=args.asset_jpeg_quality,
        playlist_loop=args.asset_playlist_loop,
    )


def ensure_vlm_artifacts(args: argparse.Namespace) -> None:
    if args.vlm_mode == "stub" or args.vlm_max_calls == 0:
        return
    if args.vlm_mode == "rkllm_multimodal":
        required = {
            "--rkllm-mm-wrapper": args.rkllm_mm_wrapper,
            "--rkllm-mm-runner": args.rkllm_mm_runner,
            "--vision-model": args.vision_model,
            "--decoder-model": args.decoder_model,
        }
    elif args.vlm_mode == "rkllm_multimodal_resident":
        required = {
            "--vision-model": args.vision_model,
            "--decoder-model": args.decoder_model,
        }
        if args.rkllm_mm_resident_runner:
            required["--rkllm-mm-resident-runner"] = args.rkllm_mm_resident_runner
    elif args.vlm_mode in {"llama_cpp_multimodal_once", "llama_cpp_multimodal_resident"}:
        required = {
            "--vlm-model-path": args.vlm_model_path,
            "--mmproj-path": args.mmproj_path,
        }
        server_bin = resolve_llama_server_bin(args)
        required["resolved_vlm_llama_server_bin"] = server_bin
    else:
        raise SystemExit(f"unsupported --vlm-mode: {args.vlm_mode}")

    missing = [f"{label}={path}" for label, path in required.items() if not path or not Path(path).exists()]
    if missing:
        raise SystemExit("missing required async VLM artifact(s): " + ", ".join(missing))


def resolve_llama_server_bin(args: argparse.Namespace) -> Path:
    if args.vlm_llama_server_bin:
        return Path(args.vlm_llama_server_bin)
    if args.llama_server_bin:
        return Path(args.llama_server_bin)
    if args.llama_bin:
        llama_cli = Path(args.llama_bin)
        sibling = llama_cli.with_name("llama-server")
        if sibling.exists():
            return sibling
    which = shutil.which("llama-server")
    if which:
        return Path(which)
    return Path("llama-server")


def rebuild_outputs(
    *,
    args: argparse.Namespace,
    combo: dict[str, Any],
    ordered_events: list[dict[str, Any]],
    vlm_by_event: dict[str, dict[str, Any]],
    alarm_output: Path,
    benchmark_output: Path,
) -> None:
    llm_input_path = Path(args.llm_input) if args.llm_input else None
    llm_by_event = (
        index_by_event_id(read_jsonl(llm_input_path))
        if llm_input_path and llm_input_path.exists()
        else {}
    )
    alarms = [
        build_alarm(event, combo, llm_by_event, vlm_by_event, {}, str(alarm_output))
        for event in ordered_events
    ]
    for alarm in alarms:
        alarm["evidence"]["event_package_path"] = str(args.events_input)
    write_jsonl(alarm_output, alarms)
    alarms_by_event = {alarm["event_id"]: alarm for alarm in alarms}
    benchmark_rows = [
        build_raw_row(
            event,
            alarms_by_event.get(event.get("event_id")),
            combo,
            args.board,
            args.environment_baseline_id,
            args.events_input,
            alarm_output,
            run_id_override=args.run_id,
        )
        for event in ordered_events
    ]
    write_jsonl(benchmark_output, benchmark_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project5 async VLM enrichment worker that tails an event package JSONL.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--board", required=True, choices=["jetson_8gb", "rk3588_8gb", "pc"])
    parser.add_argument("--environment-baseline-id", required=True)
    parser.add_argument("--events-input", required=True, type=Path)
    parser.add_argument("--llm-input", default="")
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--asset-mode", choices=["none", "source_media"], default="none")
    parser.add_argument("--asset-source-type", choices=["video_file", "video_playlist", "frame_cache_dir"], default="")
    parser.add_argument("--asset-source-uri", type=Path, default=None)
    parser.add_argument("--asset-dir", type=Path, default=None)
    parser.add_argument("--asset-playlist-loop", action="store_true")
    parser.add_argument("--asset-image-ext", choices=["jpg", "png"], default="jpg")
    parser.add_argument("--asset-jpeg-quality", type=int, default=92)
    parser.add_argument(
        "--vlm-mode",
        choices=[
            "stub",
            "rkllm_multimodal",
            "rkllm_multimodal_resident",
            "llama_cpp_multimodal_once",
            "llama_cpp_multimodal_resident",
        ],
        default="llama_cpp_multimodal_once",
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
    parser.add_argument("--llama-bin", default="llama-cli")
    parser.add_argument("--llama-server-bin", default="")
    parser.add_argument("--vlm-llama-server-bin", default="")
    parser.add_argument("--vlm-llama-server-host", default="127.0.0.1")
    parser.add_argument("--vlm-llama-server-port", type=int, default=0)
    parser.add_argument("--vlm-llama-server-no-jinja", action="store_true")
    parser.add_argument("--vlm-no-kv-offload", action="store_true")
    parser.add_argument("--vlm-no-mmproj-offload", action="store_true")
    parser.add_argument("--vlm-device", default="")
    parser.add_argument("--vision-model", type=Path, default=None)
    parser.add_argument("--decoder-model", type=Path, default=None)
    parser.add_argument("--vlm-metrics-dir", type=Path, default=None)
    parser.add_argument("--vlm-runtime-log-dir", type=Path, default=None)
    parser.add_argument("--vlm-ctx", type=int, default=1536)
    parser.add_argument("--vlm-max-tokens", type=int, default=96)
    parser.add_argument("--vlm-temperature", type=float, default=0.0)
    parser.add_argument("--vlm-timeout-ms", type=int, default=180000)
    parser.add_argument("--vlm-startup-timeout-ms", type=int, default=180000)
    parser.add_argument("--vlm-max-calls", type=int, default=2)
    parser.add_argument("--vlm-request-retries", type=int, default=0)
    parser.add_argument("--vlm-retry-backoff-sec", type=float, default=0.0)
    parser.add_argument("--vlm-once-prewarm-request", action="store_true")
    parser.add_argument("--vlm-once-prewarm-max-tokens", type=int, default=0)
    parser.add_argument("--vlm-ngl", type=int, default=0)
    parser.add_argument("--vlm-image-min-tokens", type=int, default=512)
    parser.add_argument("--vlm-image-max-tokens", type=int, default=512)
    parser.add_argument("--npu-core-num", type=int, default=3)
    parser.add_argument("--vlm-img-start", default="<|vision_start|>")
    parser.add_argument("--vlm-img-end", default="<|vision_end|>")
    parser.add_argument("--vlm-img-content", default="<|image_pad|>")
    parser.add_argument("--vlm-template-style", default="qwen")
    parser.add_argument("--poll-interval-sec", type=float, default=0.5)
    parser.add_argument("--startup-wait-sec", type=float, default=60.0)
    parser.add_argument("--idle-timeout-sec", type=float, default=0.0)
    parser.add_argument("--stop-after-budget", action="store_true")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--vlm-output", type=Path, default=None)
    parser.add_argument("--alarm-output", type=Path, default=None)
    parser.add_argument("--benchmark-output", type=Path, default=None)
    parser.add_argument("--service-log", type=Path, default=None)
    args = parser.parse_args()

    defaults = default_paths(args.board, args.run_id)
    args.vlm_output = args.vlm_output or defaults["vlm"]
    args.alarm_output = args.alarm_output or defaults["alarms"]
    args.benchmark_output = args.benchmark_output or defaults["benchmark"]
    args.service_log = args.service_log or defaults["service_log"]
    if args.asset_mode == "source_media":
        if not args.asset_source_type:
            raise SystemExit("--asset-source-type is required when --asset-mode=source_media")
        if args.asset_source_uri is None:
            raise SystemExit("--asset-source-uri is required when --asset-mode=source_media")
        if args.asset_dir is None:
            raise SystemExit("--asset-dir is required when --asset-mode=source_media")
    return args


def main() -> int:
    global STOP_REQUESTED
    args = parse_args()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    if not args.model_config.exists():
        raise SystemExit(f"--model-config not found: {args.model_config}")
    if args.llm_input and not Path(args.llm_input).exists():
        log_line(args.service_log, f"warning llm_input_missing path={args.llm_input}")

    ensure_vlm_artifacts(args)
    combo = parse_simple_yaml(args.model_config)
    args.vlm_output.parent.mkdir(parents=True, exist_ok=True)
    args.alarm_output.parent.mkdir(parents=True, exist_ok=True)
    args.benchmark_output.parent.mkdir(parents=True, exist_ok=True)
    args.service_log.parent.mkdir(parents=True, exist_ok=True)

    asset_worker = build_asset_worker(args)
    vlm_worker = ServiceVlmWorker(args.vlm_mode, combo.get("image_vlm", {}), args, args.vlm_output)
    writer = JsonlWriter(args.vlm_output)

    seen_event_ids: set[str] = set()
    ordered_events: list[dict[str, Any]] = []
    vlm_by_event: dict[str, dict[str, Any]] = {}
    offset = 0
    partial = ""
    processed_rows = 0
    last_new_event_at = time.monotonic()
    deadline = time.monotonic() + max(0.0, args.startup_wait_sec)

    log_line(
        args.service_log,
        (
            f"async_vlm_start run_id={args.run_id} board={args.board} mode={args.vlm_mode} "
            f"events_input={args.events_input} llm_input={args.llm_input or 'none'}"
        ),
    )
    log_line(
        args.service_log,
        "asset_worker_info "
        + " ".join(f"{key}={value}" for key, value in asset_worker.runtime_info().items() if value is not None),
    )
    log_line(
        args.service_log,
        "vlm_worker_info "
        + " ".join(f"{key}={value}" for key, value in vlm_worker.runtime_info().items() if value is not None),
    )

    try:
        while not STOP_REQUESTED:
            if not args.events_input.exists():
                if time.monotonic() > deadline:
                    raise SystemExit(f"events input was not created within startup wait: {args.events_input}")
                time.sleep(args.poll_interval_sec)
                continue

            current_size = args.events_input.stat().st_size
            if current_size < offset:
                log_line(args.service_log, f"events_input_truncated reset_offset old={offset} new={current_size}")
                offset = 0
                partial = ""

            with args.events_input.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                chunk = handle.read()
                offset = handle.tell()

            if chunk:
                lines, partial = complete_jsonl_lines(partial + chunk)
                for line in lines:
                    event = json.loads(line)
                    event_id = str(event.get("event_id") or "")
                    if not event_id or event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)
                    enriched_event = asset_worker.enrich(dict(event)) if args.asset_mode == "source_media" else dict(event)
                    ordered_events.append(enriched_event)
                    row = vlm_worker.review(enriched_event, utc_now_iso())
                    writer.write(row)
                    vlm_by_event[event_id] = row
                    processed_rows += 1
                    last_new_event_at = time.monotonic()
                    log_line(
                        args.service_log,
                        (
                            f"async_vlm_event event_id={event_id} status={row.get('status')} "
                            f"mode={row.get('mode')} image_path={row.get('image_path')}"
                        ),
                    )
                    rebuild_outputs(
                        args=args,
                        combo=combo,
                        ordered_events=ordered_events,
                        vlm_by_event=vlm_by_event,
                        alarm_output=args.alarm_output,
                        benchmark_output=args.benchmark_output,
                    )
                    if args.max_events > 0 and processed_rows >= args.max_events:
                        STOP_REQUESTED = True
                        break
                    if args.stop_after_budget and args.vlm_max_calls >= 0 and vlm_worker.call_count >= args.vlm_max_calls:
                        STOP_REQUESTED = True
                        break
            elif args.idle_timeout_sec > 0 and time.monotonic() - last_new_event_at >= args.idle_timeout_sec:
                log_line(args.service_log, f"async_vlm_idle_timeout seconds={args.idle_timeout_sec}")
                break

            if STOP_REQUESTED:
                break
            time.sleep(args.poll_interval_sec)
    finally:
        if ordered_events:
            rebuild_outputs(
                args=args,
                combo=combo,
                ordered_events=ordered_events,
                vlm_by_event=vlm_by_event,
                alarm_output=args.alarm_output,
                benchmark_output=args.benchmark_output,
            )
        writer.close()
        asset_worker.close()
        vlm_worker.close()

    pass_rows = [row for row in vlm_by_event.values() if row.get("status") == "pass"]
    bad_rows = [row for row in vlm_by_event.values() if row.get("status") not in {"pass", "not_executed", "fallback", "failed", "blocked_no_image_asset"}]
    log_line(
        args.service_log,
        (
            f"async_vlm_stop processed_rows={processed_rows} "
            f"pass_rows={len(pass_rows)} bad_rows={len(bad_rows)} "
            f"model_calls={vlm_worker.call_count} fallback_count={vlm_worker.fallback_count}"
        ),
    )
    print(f"async_vlm_rows={processed_rows}")
    print(f"async_vlm_pass_rows={len(pass_rows)}")
    print(f"async_vlm_bad_rows={len(bad_rows)}")
    print(f"async_vlm_model_calls={vlm_worker.call_count}")
    print(f"async_vlm_vlm_output={args.vlm_output}")
    print(f"async_vlm_alarm_output={args.alarm_output}")
    print(f"async_vlm_benchmark_output={args.benchmark_output}")
    print(f"async_vlm_service_log={args.service_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
