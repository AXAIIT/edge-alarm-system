#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from common import parse_simple_yaml, read_jsonl, utc_now_iso, write_jsonl

SERVICE_DIR = Path(__file__).resolve().parents[1] / "service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from rkllm_resident_vlm_client import ResidentRkllmVlmClient  # noqa: E402


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)[:160] or "event"


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"metrics_parse_error": str(exc)}


def build_prompt(event: dict[str, Any]) -> str:
    detections = []
    for det in event.get("detections") or []:
        detections.append(
            {
                "class_name": det.get("class_name"),
                "confidence": det.get("confidence"),
                "bbox": det.get("bbox"),
            }
        )
    input_mode = infer_vlm_input_mode(event)
    if input_mode == "temporal_frames":
        task_instruction = (
            "输入为按时间顺序排列的多关键帧拼图。先逐帧描述，再比较可见变化；"
            "只有多帧共同支持时才能陈述时间变化，不得推断画面外行为。"
        )
    elif input_mode in {"relation_context_crop", "full_keyframe"}:
        task_instruction = (
            "描述同一画面中可见对象的空间关系和场景上下文；只陈述图像能够支持的关系，"
            "不得把单帧共现扩展成接近、离开、追逐等时间行为。"
        )
    else:
        task_instruction = "只复核当前目标的可见属性、遮挡和局部状态；不得推断画面外对象或对象关系。"
    return (
        "<image>\n"
        "你是边缘告警视觉复核模块。只根据图片和下面的检测事实回答，"
        "不要新增不存在的目标，不要改写 detector 类别、置信度或 bbox。"
        f"当前视觉输入模式为 {input_mode}。{task_instruction}"
        "直接用两行简洁中文输出："
        "1) 当前输入范围内的可见证据；"
        "2) 不确定性或证据限制。\n"
        f"event_id: {event.get('event_id')}\n"
        f"alarm_domain: {event.get('alarm_domain')}\n"
        f"alarm_type: {event.get('alarm_type')}\n"
        f"trigger_rule_id: {event.get('trigger_rule_id')}\n"
        f"detections: {detections}\n"
    )


def infer_vlm_input_mode(event: dict[str, Any]) -> str:
    explicit = str(event.get("vlm_input_mode") or "").strip()
    if explicit == "temporal_frames_required":
        explicit = "temporal_frames"
    if explicit in {"object_roi", "relation_context_crop", "full_keyframe", "temporal_frames"}:
        return explicit
    if event.get("alarm_type") == "multi_object_scene" or len(event.get("detections") or []) > 1:
        return "relation_context_crop"
    return "object_roi"


def select_image_path(event: dict[str, Any]) -> tuple[Path | None, str]:
    input_mode = infer_vlm_input_mode(event)
    if input_mode == "temporal_frames":
        raw_temporal = event.get("temporal_contact_sheet_path")
        if raw_temporal:
            path = Path(str(raw_temporal))
            if path.exists():
                return path, "temporal_contact_sheet_path"
        return None, "missing_temporal_contact_sheet"
    if input_mode in {"relation_context_crop", "full_keyframe"}:
        if input_mode == "relation_context_crop":
            raw_context = event.get("context_crop_path")
            if raw_context:
                path = Path(str(raw_context))
                if path.exists():
                    return path, "context_crop_path"
        raw_keyframe = event.get("keyframe_path")
        if raw_keyframe:
            path = Path(str(raw_keyframe))
            if path.exists():
                return path, "keyframe_path"
        for raw in event.get("keyframe_paths") or []:
            path = Path(str(raw))
            if path.exists():
                return path, "keyframe_paths[0]"
        return None, "missing_context_image"

    for raw in event.get("roi_paths") or []:
        path = Path(str(raw))
        if path.exists():
            return path, "roi_paths[0]"
    raw_keyframe = event.get("keyframe_path")
    if raw_keyframe:
        path = Path(str(raw_keyframe))
        if path.exists():
            return path, "keyframe_path"
    return None, "missing"


def build_rkllm_multimodal_command(
    args: argparse.Namespace,
    event: dict[str, Any],
    image_path: Path,
    metrics_json: Path,
    output_path: Path,
) -> list[str]:
    return [
        "bash",
        str(args.rkllm_mm_wrapper),
        "--runner",
        str(args.rkllm_mm_runner),
        "--vision",
        str(args.vision_model),
        "--decoder",
        str(args.decoder_model),
        "--image",
        str(image_path),
        "--prompt",
        build_prompt(event),
        "--metrics-json",
        str(metrics_json),
        "--output-path",
        str(output_path),
        "--max-output-tokens",
        str(args.max_tokens),
        "--max-context-len",
        str(args.ctx),
        "--npu-core-num",
        str(args.npu_core_num),
        "--img-start",
        args.img_start,
        "--img-end",
        args.img_end,
        "--img-content",
        args.img_content,
        "--template-style",
        args.template_style,
        "--timeout-sec",
        str(max(1, int(args.timeout_ms / 1000))),
    ]


def build_stub_row(event: dict[str, Any], image_cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "timestamp": utc_now_iso(),
        "model": image_cfg.get("model", "unknown_vlm"),
        "mode": "stub_not_model_execution",
        "vlm_summary": None,
        "roi_count": len(event.get("roi_boxes") or []),
        "image_path": None,
        "image_source_field": None,
        "timeout_ms": args.timeout_ms,
        "image_preprocess_ms": None,
        "vlm_total_ms": None,
        "decode_tokens_per_s": None,
        "prompt_tokens": None,
        "output_tokens": None,
        "metrics_json_path": None,
        "runtime_log_path": None,
        "status": "not_executed",
    }


def run_rkllm_multimodal(event: dict[str, Any], image_cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    image_path, image_source = select_image_path(event)
    metrics_dir = args.metrics_dir or (args.output.parent / f"{args.output.stem}_vlm_metrics")
    log_dir = args.runtime_log_dir or (args.output.parent / f"{args.output.stem}_vlm_logs")
    metrics_json = metrics_dir / f"{safe_name(event.get('event_id'))}.json"
    runtime_log = log_dir / f"{safe_name(event.get('event_id'))}.log"
    metrics_json.parent.mkdir(parents=True, exist_ok=True)
    runtime_log.parent.mkdir(parents=True, exist_ok=True)
    if image_path is None:
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal",
            "vlm_summary": None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": None,
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": None,
            "vlm_total_ms": None,
            "decode_tokens_per_s": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "metrics_json_path": str(metrics_json),
            "runtime_log_path": str(runtime_log),
            "status": "blocked_no_image_asset",
        }

    command = build_rkllm_multimodal_command(args, event, image_path, metrics_json, runtime_log)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, args.timeout_ms / 1000.0 + 5.0),
        )
        total_ms = (time.monotonic() - started) * 1000.0
        combined_output = "\n".join(part.strip() for part in [proc.stdout, proc.stderr] if part and part.strip())
        if combined_output:
            runtime_log.write_text(combined_output + "\n", encoding="utf-8")
        metrics = load_metrics(metrics_json)
        summary = metrics.get("output_text") or ""
        status = "pass" if proc.returncode == 0 and summary and metrics.get("status") == "pass" else "failed"
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal",
            "vlm_summary": summary or None,
            "vlm_raw_output": combined_output or None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": str(image_path),
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": metrics.get("image_preprocess_time_ms"),
            "vlm_total_ms": metrics.get("total_time_ms") or round(total_ms, 3),
            "decode_tokens_per_s": metrics.get("decode_tokens_per_s"),
            "prompt_tokens": metrics.get("prompt_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "metrics_json_path": str(metrics_json),
            "runtime_log_path": str(runtime_log),
            "exit_code": proc.returncode,
            "metrics_status": metrics.get("status"),
            "metrics_error": metrics.get("error") or metrics.get("metrics_parse_error"),
            "status": status,
        }
    except subprocess.TimeoutExpired as exc:
        total_ms = (time.monotonic() - started) * 1000.0
        runtime_log.write_text(str(exc) + "\n", encoding="utf-8")
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal",
            "vlm_summary": None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": str(image_path),
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": None,
            "vlm_total_ms": round(total_ms, 3),
            "decode_tokens_per_s": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "metrics_json_path": str(metrics_json),
            "runtime_log_path": str(runtime_log),
            "exit_code": None,
            "metrics_status": None,
            "metrics_error": str(exc),
            "status": "timeout",
        }


def run_rkllm_multimodal_resident(
    event: dict[str, Any],
    image_cfg: dict[str, Any],
    args: argparse.Namespace,
    client: ResidentRkllmVlmClient,
) -> dict[str, Any]:
    image_path, image_source = select_image_path(event)
    if image_path is None:
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal_resident",
            "vlm_summary": None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": None,
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": None,
            "vlm_total_ms": None,
            "decode_tokens_per_s": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "metrics_json_path": None,
            "runtime_log_path": str(client.runtime_log_path),
            "status": "blocked_no_image_asset",
        }
    try:
        response = client.request(
            request_id=str(event["event_id"]),
            image_path=str(image_path),
            prompt=build_prompt(event),
            max_output_tokens=args.max_tokens,
            timeout_sec=max(1.0, args.timeout_ms / 1000.0),
        )
        summary = response.get("output_text") or ""
        status = "pass" if response.get("status") == "ok" and summary else "failed"
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal_resident",
            "vlm_summary": summary or None,
            "vlm_raw_output": summary or None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": str(image_path),
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": response.get("image_preprocess_time_ms"),
            "vlm_total_ms": response.get("total_time_ms"),
            "decode_tokens_per_s": response.get("decode_tokens_per_s"),
            "prompt_tokens": response.get("prompt_tokens"),
            "output_tokens": response.get("output_tokens"),
            "metrics_json_path": None,
            "runtime_log_path": str(client.runtime_log_path),
            "exit_code": response.get("exit_code"),
            "metrics_status": response.get("status"),
            "metrics_error": response.get("error"),
            "resident_server_pid": response.get("pid"),
            "resident_model_load_count": response.get("model_load_count"),
            "resident_request_index": response.get("request_index"),
            "status": status,
        }
    except Exception as exc:
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": image_cfg.get("model", "unknown_vlm"),
            "mode": "rkllm_multimodal_resident",
            "vlm_summary": None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": str(image_path),
            "image_source_field": image_source,
            "timeout_ms": args.timeout_ms,
            "image_preprocess_ms": None,
            "vlm_total_ms": None,
            "decode_tokens_per_s": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "metrics_json_path": None,
            "runtime_log_path": str(client.runtime_log_path),
            "metrics_error": str(exc),
            "status": "failed",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project 08 task-driven VLM routing and optional real multimodal execution.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--mode", choices=["stub", "rkllm_multimodal", "rkllm_multimodal_resident"], default="stub")
    parser.add_argument("--rkllm-mm-wrapper", type=Path, default=Path("projects/08_alarm_system/scripts/service/runtime_adapters/run_rkllm_multimodal_once.sh"))
    parser.add_argument("--rkllm-mm-runner", type=Path, default=Path("projects/08_alarm_system/runners/rkllm_multimodal_once/build/rkllm_multimodal_once"))
    parser.add_argument("--rkllm-mm-resident-runner", type=Path, default=Path("projects/08_alarm_system/runners/rkllm_resident_vlm_server/build/rkllm_resident_vlm_server"))
    parser.add_argument("--vision-model", type=Path, default=None)
    parser.add_argument("--decoder-model", type=Path, default=None)
    parser.add_argument("--metrics-dir", type=Path, default=None)
    parser.add_argument("--runtime-log-dir", type=Path, default=None)
    parser.add_argument("--ctx", type=int, default=2048)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--npu-core-num", type=int, default=3)
    parser.add_argument("--img-start", default="<|vision_start|>")
    parser.add_argument("--img-end", default="<|vision_end|>")
    parser.add_argument("--img-content", default="<|image_pad|>")
    parser.add_argument("--template-style", default="qwen")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--startup-timeout-ms", type=int, default=30000)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    events = read_jsonl(args.events)
    if args.max_events:
        events = events[: args.max_events]
    model_config = parse_simple_yaml(args.model_config)
    image_cfg = model_config.get("image_vlm", {})

    if args.mode == "rkllm_multimodal":
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
            raise SystemExit("missing required real VLM artifact(s): " + ", ".join(missing))
        rows = [run_rkllm_multimodal(event, image_cfg, args) for event in events]
    elif args.mode == "rkllm_multimodal_resident":
        missing = []
        for label, path in [
            ("--rkllm-mm-resident-runner", args.rkllm_mm_resident_runner),
            ("--vision-model", args.vision_model),
            ("--decoder-model", args.decoder_model),
        ]:
            if path is None or not Path(path).exists():
                missing.append(f"{label}={path}")
        if missing:
            raise SystemExit("missing required resident VLM artifact(s): " + ", ".join(missing))
        runtime_log_dir = args.runtime_log_dir or (args.output.parent / f"{args.output.stem}_vlm_runtime")
        runtime_log_path = runtime_log_dir / "rkllm_resident_vlm_server.log"
        client = ResidentRkllmVlmClient(
            runner=args.rkllm_mm_resident_runner,
            vision_model=str(args.vision_model),
            decoder_model=str(args.decoder_model),
            max_context_len=args.ctx,
            npu_core_num=args.npu_core_num,
            runtime_log_path=runtime_log_path,
            startup_timeout_sec=max(1.0, args.startup_timeout_ms / 1000.0),
            img_start=args.img_start,
            img_end=args.img_end,
            img_content=args.img_content,
            template_style=args.template_style,
        )
        client.start()
        try:
            rows = [run_rkllm_multimodal_resident(event, image_cfg, args, client) for event in events]
        finally:
            client.close()
    else:
        rows = [build_stub_row(event, image_cfg, args) for event in events]

    count = write_jsonl(args.output, rows)
    print(f"vlm_rows_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
