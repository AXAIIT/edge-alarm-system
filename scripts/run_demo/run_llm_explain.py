#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import select
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from common import parse_simple_yaml, read_jsonl, risk_from_detections, utc_now_iso, write_jsonl


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RKLLM_RUNTIME_LINE_RE = re.compile(
    r"^\s*(?:[IWEF]\s+rkllm:|rkllm[-_ ]runtime\b|loading\s+rkllm\s+model\b|rkllm_init\b)",
    flags=re.IGNORECASE,
)


def token_approx(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def normalize_terminal_output(text: str) -> str:
    text = ANSI_RE.sub("", text or "")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def safe_session_name(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", text or "event").strip("_")
    return (safe or "event")[:180]


def build_prompt(event: dict, *, qwen_no_think: bool = False) -> str:
    detections = []
    for det in event.get("detections") or []:
        detections.append(
            {
                "class_name": det.get("class_name"),
                "class_id": det.get("class_id"),
                "confidence": det.get("confidence"),
                "bbox": det.get("bbox"),
            }
        )
    if qwen_no_think:
        output_instruction = (
            "不要输出思考过程、推理过程、分析过程或 [Start thinking]。"
            "直接用简洁中文输出四行：1) 触发原因；2) 风险等级；3) 建议动作；4) 证据限制。\n"
        )
    else:
        output_instruction = (
            "可以先思考，但最终必须在 [End thinking] 后用简洁中文输出四行："
            "1) 触发原因；2) 风险等级；3) 建议动作；4) 证据限制。\n"
        )
    prompt = (
        "你是边缘告警解释系统。只根据输入 JSON 中的检测事实解释告警，"
        "不要新增不存在的目标，不要改写类别、置信度或 bbox，"
        "不要推断行为、身份、装备、违法、火焰、烟雾、跌倒或其他未给出的场景属性。\n"
        f"{output_instruction}"
        f"event_id: {event.get('event_id')}\n"
        f"alarm_domain: {event.get('alarm_domain')}\n"
        f"alarm_type: {event.get('alarm_type')}\n"
        f"trigger_rule_id: {event.get('trigger_rule_id')}\n"
        f"trigger_reason: {event.get('trigger_reason')}\n"
        f"detections: {detections}\n"
    )
    if qwen_no_think:
        prompt += "/no_think\n"
    return prompt


def extract_final_answer(output: str) -> str:
    if not output:
        return output
    output = normalize_terminal_output(output)
    marker = "[End thinking]"
    if marker in output:
        output = output.rsplit(marker, 1)[1]
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == ">":
            continue
        if stripped == "Exiting...":
            continue
        if stripped.startswith("[ Prompt:"):
            continue
        if stripped.startswith("Script started"):
            continue
        if stripped.startswith("Script done"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def clean_rkllm_output(output: str) -> str:
    """Drop RKLLM runtime banner/log lines while preserving generated text."""
    output = normalize_terminal_output(output)
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if RKLLM_RUNTIME_LINE_RE.search(stripped):
            continue
        if "rkllm-runtime version" in stripped.lower():
            continue
        if "loading rkllm model" in stripped.lower():
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def has_rkllm_runtime_log(output: str) -> bool:
    output = normalize_terminal_output(output)
    for line in output.splitlines():
        stripped = line.strip()
        if RKLLM_RUNTIME_LINE_RE.search(stripped):
            return True
        lower = stripped.lower()
        if "rkllm-runtime version" in lower or "loading rkllm model" in lower:
            return True
    return False


def llama_output_is_error(output: str, stderr: str, returncode: int) -> bool:
    combined = f"{output}\n{stderr}".lower()
    error_markers = [
        "unknown argument",
        "is not supported",
        "invalid argument",
        "error: request",
    ]
    return any(marker in combined for marker in error_markers)


def parse_llama_decode_tps(stderr: str) -> float | None:
    patterns = [
        r"eval time\s*=\s*[^,]+,\s*\d+\s+runs?\s*,\s*([0-9.]+)\s*tokens per second",
        r"([0-9.]+)\s+tokens per second",
        r"([0-9.]+)\s+tok/s",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, stderr, flags=re.IGNORECASE)
        if matches:
            try:
                return float(matches[-1])
            except ValueError:
                return None
    return None


def load_metrics_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"metrics_parse_error": str(exc)}


def build_llama_command(args: argparse.Namespace, prompt: str) -> list[str]:
    command = [
        args.llama_bin,
        "-m",
        args.model_path,
        "-p",
        prompt,
        "-n",
        str(args.max_tokens),
        "-c",
        str(args.ctx),
        "--temp",
        str(args.temperature),
        "--no-display-prompt",
    ]
    # Keep --no-conversation as a compatibility flag for older runbooks, but
    # do not forward it: Jetson llama.cpp b9777 llama-cli reports it as unsupported.
    if args.ngl is not None:
        command.extend(["-ngl", str(args.ngl)])
    for extra in args.extra_arg or []:
        command.append(extra)
    if "--single-turn" not in command:
        command.append("--single-turn")
    return command


def run_subprocess_capture(command: list[str], timeout_s: float) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_pty_capture(command: list[str], timeout_s: float) -> tuple[int, str, str]:
    import pty

    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout_s
    try:
        while True:
            if proc.poll() is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                raise subprocess.TimeoutExpired(command, timeout_s)
            ready, _, _ = select.select([master_fd], [], [], min(0.2, remaining))
            if ready:
                try:
                    data = os.read(master_fd, 8192)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0)
            if not ready:
                break
            try:
                data = os.read(master_fd, 8192)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
    finally:
        os.close(master_fd)
    output = b"".join(chunks).decode("utf-8", errors="replace")
    return proc.wait(), output, ""


def run_script_capture(command: list[str], timeout_s: float, session_log: Path) -> tuple[int, str, str]:
    script_bin = shutil.which("script")
    if not script_bin:
        return 127, "", "script command not found; install util-linux or use --capture-mode pty"

    session_log.parent.mkdir(parents=True, exist_ok=True)
    command_text = " ".join(shlex.quote(str(part)) for part in command)
    wrapper = [script_bin, "-q", "-e", "-c", command_text, str(session_log)]
    proc = subprocess.run(
        wrapper,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
    )
    session_text = ""
    if session_log.exists():
        session_text = session_log.read_text(encoding="utf-8", errors="replace")
    outer_text = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    if outer_text and outer_text not in session_text:
        session_text = "\n".join(part for part in [session_text, outer_text] if part)
    return proc.returncode, session_text, ""


def run_command_capture(
    command: list[str],
    timeout_s: float,
    capture_mode: str,
    session_log: Path | None,
) -> tuple[int, str, str, str]:
    """Capture llama.cpp output, including builds that write through a terminal."""
    selected_mode = capture_mode
    if capture_mode == "auto":
        if os.name == "posix" and shutil.which("script"):
            selected_mode = "script"
        elif os.name == "posix":
            selected_mode = "pty"
        else:
            selected_mode = "subprocess"

    if selected_mode == "script":
        if session_log is None:
            raise ValueError("session_log is required for script capture mode")
        returncode, stdout, stderr = run_script_capture(command, timeout_s, session_log)
    elif selected_mode == "pty":
        if os.name != "posix":
            returncode, stdout, stderr = run_subprocess_capture(command, timeout_s)
            selected_mode = "subprocess"
        else:
            returncode, stdout, stderr = run_pty_capture(command, timeout_s)
    else:
        returncode, stdout, stderr = run_subprocess_capture(command, timeout_s)
        selected_mode = "subprocess"

    return returncode, stdout, stderr, selected_mode


def run_llama_cpp(event: dict, model_config: dict, args: argparse.Namespace) -> dict:
    prompt = build_prompt(event, qwen_no_think=args.qwen_no_think)
    text_model = model_config.get("text_llm", {}).get("model", "llama_cpp_text_model")
    command = build_llama_command(args, prompt)
    session_log = None
    if args.capture_mode in ("auto", "script"):
        session_dir = args.session_log_dir or (args.output.parent / f"{args.output.stem}_llama_sessions")
        session_log = session_dir / f"{safe_session_name(event.get('event_id'))}.log"
    started = time.monotonic()
    try:
        returncode, stdout, stderr, capture_mode = run_command_capture(
            command,
            max(1, args.timeout_ms / 1000.0),
            args.capture_mode,
            session_log,
        )
        total_ms = (time.monotonic() - started) * 1000.0
        stdout = normalize_terminal_output(stdout).strip()
        stderr = normalize_terminal_output(stderr).strip()
        combined_output = "\n".join(part for part in [stdout, stderr] if part)
        final_output = extract_final_answer(combined_output)
        is_error = llama_output_is_error(stdout, stderr, returncode)
        status = "pass" if final_output and not is_error else "failed"
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": text_model,
            "mode": "llama_cpp",
            "capture_mode": capture_mode,
            "session_log_path": str(session_log) if session_log else None,
            "llm_explanation": final_output or None,
            "llm_raw_output": combined_output or None,
            "thinking_included": "[Start thinking]" in combined_output or "[End thinking]" in combined_output,
            "risk_level": risk_from_detections(event.get("detections") or []),
            "first_token_ms": None,
            "prefill_ms": None,
            "decode_tokens_per_s": parse_llama_decode_tps(combined_output),
            "total_ms": round(total_ms, 3),
            "prompt_tokens": token_approx(prompt),
            "output_tokens": token_approx(combined_output),
            "final_output_tokens": token_approx(final_output),
            "status": status,
            "exit_code": returncode,
            "stderr_tail": combined_output[-2000:] if combined_output else None,
        }
    except subprocess.TimeoutExpired as exc:
        total_ms = (time.monotonic() - started) * 1000.0
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": text_model,
            "mode": "llama_cpp",
            "capture_mode": args.capture_mode,
            "session_log_path": str(session_log) if session_log else None,
            "llm_explanation": None,
            "llm_raw_output": None,
            "thinking_included": None,
            "risk_level": risk_from_detections(event.get("detections") or []),
            "first_token_ms": None,
            "prefill_ms": None,
            "decode_tokens_per_s": None,
            "total_ms": round(total_ms, 3),
            "prompt_tokens": token_approx(prompt),
            "output_tokens": None,
            "final_output_tokens": None,
            "status": "timeout",
            "exit_code": None,
            "stderr_tail": str(exc)[-2000:],
        }


def build_rkllm_command(args: argparse.Namespace, prompt: str, metrics_json: Path) -> list[str]:
    command = [
        "bash",
        str(args.rkllm_wrapper),
    ]
    if args.rkllm_runner:
        command.extend(["--runner", str(args.rkllm_runner)])
    command.extend(
        [
            "--model",
            args.model_path,
            "--prompt",
            prompt,
            "--max-output-tokens",
            str(args.max_tokens),
            "--max-context-len",
            str(args.ctx),
            "--metrics-json",
            str(metrics_json),
            "--timeout-sec",
            str(max(1, int(args.timeout_ms / 1000))),
        ]
    )
    return command


def run_rkllm(event: dict, model_config: dict, args: argparse.Namespace) -> dict:
    prompt = build_prompt(event, qwen_no_think=args.qwen_no_think)
    text_model = model_config.get("text_llm", {}).get("model", "rkllm_text_model")
    metrics_dir = args.metrics_dir or (args.output.parent / f"{args.output.stem}_rkllm_metrics")
    metrics_json = metrics_dir / f"{safe_session_name(event.get('event_id'))}.json"
    metrics_json.parent.mkdir(parents=True, exist_ok=True)
    command = build_rkllm_command(args, prompt, metrics_json)
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
        stdout = normalize_terminal_output(proc.stdout).strip()
        stderr = normalize_terminal_output(proc.stderr).strip()
        combined_output = "\n".join(part for part in [stdout, stderr] if part)
        final_output = extract_final_answer(clean_rkllm_output(combined_output))
        metrics = load_metrics_json(metrics_json)
        metrics_status = metrics.get("status")
        metrics_error = metrics.get("error")
        status = "pass" if proc.returncode == 0 and final_output and not has_rkllm_runtime_log(final_output) else "failed"
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": text_model,
            "mode": "rkllm",
            "runner": str(args.rkllm_runner) if args.rkllm_runner else None,
            "wrapper": str(args.rkllm_wrapper),
            "metrics_json_path": str(metrics_json),
            "llm_explanation": final_output or None,
            "llm_raw_output": combined_output or None,
            "thinking_included": "[Start thinking]" in combined_output or "[End thinking]" in combined_output,
            "risk_level": risk_from_detections(event.get("detections") or []),
            "first_token_ms": metrics.get("first_token_latency_ms") or metrics.get("first_token_ms"),
            "prefill_ms": metrics.get("prefill_time_ms") or metrics.get("prefill_ms"),
            "decode_tokens_per_s": metrics.get("decode_tokens_per_s") or metrics.get("tokens_per_second"),
            "total_ms": metrics.get("total_time_ms") or metrics.get("total_ms") or round(total_ms, 3),
            "prompt_tokens": metrics.get("prompt_tokens") or token_approx(prompt),
            "output_tokens": metrics.get("output_tokens") or token_approx(combined_output),
            "final_output_tokens": token_approx(final_output),
            "status": status,
            "exit_code": proc.returncode,
            "metrics_status": metrics_status,
            "metrics_error": metrics_error,
            "stderr_tail": combined_output[-2000:] if combined_output else None,
        }
    except subprocess.TimeoutExpired as exc:
        total_ms = (time.monotonic() - started) * 1000.0
        return {
            "event_id": event["event_id"],
            "timestamp": utc_now_iso(),
            "model": text_model,
            "mode": "rkllm",
            "runner": str(args.rkllm_runner) if args.rkllm_runner else None,
            "wrapper": str(args.rkllm_wrapper),
            "metrics_json_path": str(metrics_json),
            "llm_explanation": None,
            "llm_raw_output": None,
            "thinking_included": None,
            "risk_level": risk_from_detections(event.get("detections") or []),
            "first_token_ms": None,
            "prefill_ms": None,
            "decode_tokens_per_s": None,
            "total_ms": round(total_ms, 3),
            "prompt_tokens": token_approx(prompt),
            "output_tokens": None,
            "final_output_tokens": None,
            "status": "timeout",
            "exit_code": None,
            "metrics_status": None,
            "metrics_error": str(exc),
            "stderr_tail": str(exc)[-2000:],
        }


def build_template_output(event: dict, model_config: dict) -> dict:
    detections = event.get("detections") or []
    risk = risk_from_detections(detections)
    text_model = model_config.get("text_llm", {}).get("model", "template_llm")
    class_parts = []
    for det in detections:
        label = det.get("class_name") or det.get("class_id")
        conf = det.get("confidence")
        class_parts.append(f"{label}:{conf:.3f}" if isinstance(conf, (int, float)) else str(label))
    summary = ", ".join(class_parts) if class_parts else "no qualifying detection"
    return {
        "event_id": event["event_id"],
        "timestamp": utc_now_iso(),
        "model": text_model,
        "mode": "template_fallback_interface_wiring",
        "llm_explanation": (
            f"Detector reported {len(detections)} qualifying object(s): {summary}. "
            f"Risk is estimated as {risk}; keep original detector boxes and classes unchanged."
        ),
        "risk_level": risk,
        "first_token_ms": None,
        "prefill_ms": None,
        "decode_tokens_per_s": None,
        "total_ms": None,
        "prompt_tokens": None,
        "output_tokens": None,
        "status": "stub",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Template LLM explanation generator for Project 05 wiring.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--prompt-template", default="")
    parser.add_argument("--mode", choices=["template", "llama_cpp", "rkllm"], default="template")
    parser.add_argument("--llama-bin", default="llama-cli")
    parser.add_argument("--rkllm-wrapper", type=Path, default=Path("projects/05_alarm_system/scripts/service/runtime_adapters/run_rkllm_single_turn.sh"))
    parser.add_argument("--rkllm-runner", type=Path, default=None)
    parser.add_argument("--metrics-dir", type=Path, default=None)
    parser.add_argument("--model-path", default="")
    parser.add_argument("--ctx", type=int, default=512)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--ngl", type=int, default=None)
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--no-conversation", action="store_true")
    parser.add_argument("--qwen-no-think", action="store_true", help="Append /no_think to suppress Qwen3 thinking output.")
    parser.add_argument(
        "--capture-mode",
        choices=["auto", "script", "pty", "subprocess"],
        default="auto",
        help="Capture backend for llama.cpp output. Jetson auto prefers util-linux script.",
    )
    parser.add_argument("--session-log-dir", type=Path, default=None)
    parser.add_argument("--extra-arg", action="append", default=[])
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    events = read_jsonl(args.events)
    if args.max_events:
        events = events[: args.max_events]
    model_config = parse_simple_yaml(args.model_config)
    if args.mode == "llama_cpp":
        if not args.model_path:
            raise SystemExit("--model-path is required when --mode llama_cpp")
        rows = [run_llama_cpp(event, model_config, args) for event in events]
    elif args.mode == "rkllm":
        if not args.model_path:
            raise SystemExit("--model-path is required when --mode rkllm")
        if not args.rkllm_wrapper.exists():
            raise SystemExit(f"--rkllm-wrapper not found: {args.rkllm_wrapper}")
        rows = [run_rkllm(event, model_config, args) for event in events]
    else:
        rows = [build_template_output(event, model_config) for event in events]
    count = write_jsonl(args.output, rows)
    print(f"llm_rows_written={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
