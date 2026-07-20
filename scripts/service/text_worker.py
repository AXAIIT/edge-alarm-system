#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

RUN_DEMO_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(RUN_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DEMO_DIR))

from rkllm_resident_client import ResidentRkllmTextClient  # noqa: E402
from llama_cpp_resident_client import ResidentLlamaCppTextClient  # noqa: E402
from run_llm_explain import build_prompt, clean_rkllm_output, extract_final_answer, run_llama_cpp, run_rkllm, token_approx  # noqa: E402


def risk_from_detections(detections: list[dict[str, Any]]) -> str:
    if not detections:
        return "info"
    max_conf = max(float(d.get("confidence", 0.0)) for d in detections)
    classes = {str(d.get("class_name") or d.get("class_id")) for d in detections}
    if max_conf >= 0.85 or {"person", "bus", "truck"} & classes:
        return "high"
    if max_conf >= 0.65:
        return "medium"
    if max_conf >= 0.40:
        return "low"
    return "info"


class TemplateTextWorker:
    def __init__(self, model_name: str = "template_text_worker") -> None:
        self.model_name = model_name
        self.call_count = 0

    def explain(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        self.call_count += 1
        detections = event.get("detections") or []
        risk = risk_from_detections(detections)
        labels = []
        for det in detections:
            label = det.get("class_name") or det.get("class_id")
            conf = det.get("confidence")
            if isinstance(conf, (int, float)):
                labels.append(f"{label}:{conf:.3f}")
            else:
                labels.append(str(label))
        summary = ", ".join(labels) if labels else "no qualifying detection"
        return {
            "event_id": event["event_id"],
            "timestamp": timestamp,
            "model": self.model_name,
            "mode": "template_fallback_service_worker",
            "llm_explanation": (
                f"1) 触发原因：规则命中 {event.get('alarm_type')}，检测摘要 {summary}\n"
                f"2) 风险等级：{risk}\n"
                "3) 建议动作：记录事件并由人工复核\n"
                "4) 证据限制：仅基于 detector event package，未执行真实常驻 LLM"
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


class ServiceTextWorker:
    def __init__(self, mode: str, model_config: dict[str, Any], args: argparse.Namespace, output_path: Path) -> None:
        self.mode = mode
        self.model_config = model_config
        self.output_path = output_path
        self.call_count = 0
        self.fallback_count = 0
        self.template_worker = TemplateTextWorker(model_config.get("text_llm", {}).get("model", "template_text_worker"))
        self.args = args
        self.resident_client: ResidentRkllmTextClient | ResidentLlamaCppTextClient | None = None
        if self.mode == "rkllm_resident" and self.args.text_max_calls != 0:
            runner = self._resolve_resident_runner()
            runtime_log_dir = self.args.text_runtime_log_dir or (
                self.output_path.parent / f"{self.output_path.stem}_rkllm_resident_runtime"
            )
            runtime_log_path = runtime_log_dir / "rkllm_resident_text_server.log"
            self.resident_client = ResidentRkllmTextClient(
                runner=runner,
                model_path=self.args.text_model_path,
                max_context_len=self.args.text_ctx,
                runtime_log_path=runtime_log_path,
                startup_timeout_sec=max(1.0, self.args.text_startup_timeout_ms / 1000.0),
                taskset_mask=self.args.rkllm_taskset_mask,
            )
            self.resident_client.start()
        elif self.mode == "llama_cpp_resident" and self.args.text_max_calls != 0:
            server_bin = self._resolve_llama_server_bin()
            runtime_log_dir = self.args.text_runtime_log_dir or (
                self.output_path.parent / f"{self.output_path.stem}_llama_cpp_resident_runtime"
            )
            runtime_log_path = runtime_log_dir / "llama_cpp_resident_text_server.log"
            self.resident_client = ResidentLlamaCppTextClient(
                server_bin=server_bin,
                model_path=self.args.text_model_path,
                max_context_len=self.args.text_ctx,
                runtime_log_path=runtime_log_path,
                startup_timeout_sec=max(1.0, self.args.text_startup_timeout_ms / 1000.0),
                host=self.args.llama_server_host,
                port=self.args.llama_server_port,
                ngl=self.args.ngl,
                parallel=1,
                temperature=self.args.text_temperature,
                jinja=not self.args.llama_server_no_jinja,
                no_kv_offload=self.args.text_no_kv_offload,
                device=self.args.text_device,
            )
            self.resident_client.start()

    def explain(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        if self.mode == "template":
            self.fallback_count += 1
            return self.template_worker.explain(event, timestamp)
        if self.args.text_max_calls >= 0 and self.call_count >= self.args.text_max_calls:
            self.fallback_count += 1
            row = self.template_worker.explain(event, timestamp)
            row["mode"] = f"{self.mode}_budget_exhausted_template_fallback"
            row["status"] = "stub"
            return row
        self.call_count += 1
        if self.mode == "llama_cpp":
            return run_llama_cpp(event, self.model_config, self._llama_args())
        if self.mode == "llama_cpp_resident":
            return self._run_llama_cpp_resident(event, timestamp)
        if self.mode == "rkllm":
            return run_rkllm(event, self.model_config, self._rkllm_args())
        if self.mode == "rkllm_resident":
            return self._run_rkllm_resident(event, timestamp)
        raise ValueError(f"unsupported text worker mode: {self.mode}")

    def close(self) -> None:
        if self.resident_client is not None:
            self.resident_client.close()

    def runtime_info(self) -> dict[str, Any]:
        if self.resident_client is None:
            return {"mode": self.mode}
        if self.mode == "llama_cpp_resident":
            server_bin = self._resolve_llama_server_bin()
            return {
                "mode": self.mode,
                "server_bin": str(server_bin),
                "server_pid": self.resident_client.server_pid,
                "model_load_count": self.resident_client.model_load_count,
                "request_count": self.resident_client.request_count,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "host": self.args.llama_server_host,
                "port": self.resident_client.port,
                "parallel": self.resident_client.parallel,
                "ngl": self.args.ngl,
                "no_kv_offload": self.args.text_no_kv_offload,
                "device": self.args.text_device or "auto",
            }
        return {
            "mode": self.mode,
            "runner": str(self._resolve_resident_runner()),
            "server_pid": self.resident_client.server_pid,
            "model_load_count": self.resident_client.model_load_count,
            "request_count": self.resident_client.request_count,
            "runtime_log_path": str(self.resident_client.runtime_log_path),
        }

    def _llama_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            llama_bin=self.args.llama_bin,
            model_path=self.args.text_model_path,
            max_tokens=self.args.text_max_tokens,
            ctx=self.args.text_ctx,
            temperature=self.args.text_temperature,
            ngl=self.args.ngl,
            timeout_ms=self.args.text_timeout_ms,
            qwen_no_think=self.args.qwen_no_think,
            capture_mode=self.args.capture_mode,
            session_log_dir=self.args.session_log_dir,
            output=self.output_path,
            extra_arg=self.args.extra_arg or [],
            no_conversation=False,
        )

    def _rkllm_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            rkllm_wrapper=self.args.rkllm_wrapper,
            rkllm_runner=self.args.rkllm_runner,
            metrics_dir=self.args.text_metrics_dir,
            model_path=self.args.text_model_path,
            max_tokens=self.args.text_max_tokens,
            ctx=self.args.text_ctx,
            timeout_ms=self.args.text_timeout_ms,
            qwen_no_think=self.args.qwen_no_think,
            output=self.output_path,
        )

    def _resolve_resident_runner(self) -> Path:
        if self.args.rkllm_runner:
            return Path(self.args.rkllm_runner)
        candidates = [
            Path("projects/05_alarm_system/runners/rkllm_resident_text_server/build/rkllm_resident_text_server"),
            Path("build/05_alarm_system_rkllm_text/rkllm_resident_text_server"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _resolve_llama_server_bin(self) -> Path:
        if getattr(self.args, "llama_server_bin", ""):
            return Path(self.args.llama_server_bin)
        if getattr(self.args, "llama_bin", ""):
            llama_cli = Path(self.args.llama_bin)
            sibling_names = ["llama-server.exe", "llama-server"] if sys.platform.startswith("win") else ["llama-server"]
            for sibling_name in sibling_names:
                sibling = llama_cli.with_name(sibling_name)
                if sibling.exists():
                    return sibling
        which = shutil.which("llama-server")
        if which:
            return Path(which)
        return Path("llama-server")

    def _run_llama_cpp_resident(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        assert self.resident_client is not None
        prompt = build_prompt(event, qwen_no_think=self.args.qwen_no_think)
        try:
            response = self.resident_client.request(
                request_id=str(event["event_id"]),
                prompt=prompt,
                max_output_tokens=self.args.text_max_tokens,
                timeout_sec=max(1.0, self.args.text_timeout_ms / 1000.0),
            )
            raw_output = response.get("output_text") or ""
            final_output = extract_final_answer(raw_output)
            status = "pass" if response.get("status") == "ok" and final_output else "failed"
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.model_config.get("text_llm", {}).get("model", "llama_cpp_text_model"),
                "mode": "llama_cpp_resident_service_worker",
                "runner": str(self._resolve_llama_server_bin()),
                "wrapper": None,
                "metrics_json_path": None,
                "capture_mode": "http_resident",
                "session_log_path": None,
                "llm_explanation": final_output or None,
                "llm_raw_output": raw_output or None,
                "thinking_included": "[Start thinking]" in raw_output or "[End thinking]" in raw_output,
                "risk_level": risk_from_detections(event.get("detections") or []),
                "first_token_ms": response.get("first_token_ms"),
                "prefill_ms": response.get("prefill_ms"),
                "decode_tokens_per_s": response.get("decode_tokens_per_s"),
                "total_ms": response.get("total_time_ms"),
                "prompt_tokens": response.get("prompt_tokens") or token_approx(prompt),
                "output_tokens": response.get("output_tokens") or token_approx(raw_output),
                "final_output_tokens": token_approx(final_output),
                "status": status,
                "exit_code": response.get("exit_code"),
                "metrics_status": response.get("status"),
                "metrics_error": response.get("error"),
                "stderr_tail": None,
                "resident_server_pid": response.get("pid"),
                "resident_model_load_count": response.get("model_load_count"),
                "resident_request_index": response.get("request_index"),
                "runtime_log_path": str(self.resident_client.runtime_log_path),
            }
        except Exception as exc:
            self.fallback_count += 1
            row = self.template_worker.explain(event, timestamp)
            row["mode"] = "llama_cpp_resident_request_failed_template_fallback"
            row["status"] = "fallback"
            row["metrics_error"] = str(exc)
            row["runtime_log_path"] = str(self.resident_client.runtime_log_path)
            return row

    def _run_rkllm_resident(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        assert self.resident_client is not None
        prompt = build_prompt(event, qwen_no_think=self.args.qwen_no_think)
        try:
            response = self.resident_client.request(
                request_id=str(event["event_id"]),
                prompt=prompt,
                max_output_tokens=self.args.text_max_tokens,
                timeout_sec=max(1.0, self.args.text_timeout_ms / 1000.0),
            )
            raw_output = response.get("output_text") or ""
            final_output = extract_final_answer(clean_rkllm_output(raw_output))
            status = "pass" if response.get("status") == "ok" and final_output else "failed"
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.model_config.get("text_llm", {}).get("model", "rkllm_text_model"),
                "mode": "rkllm_resident_service_worker",
                "runner": str(self._resolve_resident_runner()),
                "wrapper": None,
                "metrics_json_path": None,
                "llm_explanation": final_output or None,
                "llm_raw_output": raw_output or None,
                "thinking_included": "[Start thinking]" in raw_output or "[End thinking]" in raw_output,
                "risk_level": risk_from_detections(event.get("detections") or []),
                "first_token_ms": response.get("first_token_ms"),
                "prefill_ms": response.get("prefill_ms"),
                "decode_tokens_per_s": response.get("decode_tokens_per_s"),
                "total_ms": response.get("total_time_ms"),
                "prompt_tokens": response.get("prompt_tokens") or token_approx(prompt),
                "output_tokens": response.get("output_tokens") or token_approx(raw_output),
                "final_output_tokens": token_approx(final_output),
                "status": status,
                "exit_code": response.get("exit_code"),
                "metrics_status": response.get("status"),
                "metrics_error": response.get("error"),
                "stderr_tail": None,
                "resident_server_pid": response.get("pid"),
                "resident_model_load_count": response.get("model_load_count"),
                "resident_request_index": response.get("request_index"),
                "runtime_log_path": str(self.resident_client.runtime_log_path),
            }
        except Exception as exc:
            self.fallback_count += 1
            row = self.template_worker.explain(event, timestamp)
            row["mode"] = "rkllm_resident_request_failed_template_fallback"
            row["status"] = "fallback"
            row["metrics_error"] = str(exc)
            row["runtime_log_path"] = str(self.resident_client.runtime_log_path)
            return row
