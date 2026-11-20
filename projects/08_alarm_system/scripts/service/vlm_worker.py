#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

RUN_DEMO_DIR = Path(__file__).resolve().parents[1] / "run_demo"
if str(RUN_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(RUN_DEMO_DIR))

from rkllm_resident_vlm_client import ResidentRkllmVlmClient  # noqa: E402
from llama_cpp_resident_vlm_client import ResidentLlamaCppVlmClient  # noqa: E402
from vlm_runtime_profile import PROMPT_POLICY_ID, load_runtime_profile  # noqa: E402
from run_vlm_roi_qa import build_prompt, infer_vlm_input_mode, run_rkllm_multimodal, select_image_path  # noqa: E402


def safe_name(text: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", text or "event").strip("_")
    return (safe or "event")[:180]


class StubVlmWorker:
    def __init__(self, model_name: str = "stub_vlm_worker") -> None:
        self.model_name = model_name
        self.call_count = 0

    def review(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        row = self._review(event, timestamp)
        row.setdefault("vlm_input_mode", infer_vlm_input_mode(event))
        row.setdefault("context_crop_path", event.get("context_crop_path"))
        row.setdefault("context_crop_box", event.get("context_crop_box"))
        row.setdefault("context_detection_ids", event.get("context_detection_ids") or [])
        row.setdefault("evidence_frame_ids", event.get("evidence_frame_ids") or [])
        row.setdefault("keyframe_paths", event.get("keyframe_paths") or [])
        row.setdefault("temporal_contact_sheet_path", event.get("temporal_contact_sheet_path"))
        return row

    def _review(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        self.call_count += 1
        return {
            "event_id": event["event_id"],
            "timestamp": timestamp,
            "model": self.model_name,
            "mode": "stub_not_model_execution",
            "vlm_summary": None,
            "roi_count": len(event.get("roi_boxes") or []),
            "image_path": None,
            "image_source_field": None,
            "timeout_ms": None,
            "image_preprocess_ms": None,
            "vlm_total_ms": None,
            "decode_tokens_per_s": None,
            "prompt_tokens": None,
            "output_tokens": None,
            "metrics_json_path": None,
            "runtime_log_path": None,
            "status": "not_executed",
        }


class ServiceVlmWorker:
    def __init__(self, mode: str, image_cfg: dict[str, Any], args: argparse.Namespace, output_path: Path) -> None:
        self.mode = mode
        self.image_cfg = image_cfg
        self.args = args
        self.runtime_profile = load_runtime_profile(
            image_cfg.get("runtime_profile_ref"), Path(__file__).resolve().parents[4]
        )
        self.prompt_policy = image_cfg.get("prompt_policy", PROMPT_POLICY_ID)
        if self.prompt_policy != PROMPT_POLICY_ID:
            raise ValueError("unsupported VLM prompt policy")
        if self.runtime_profile and self.runtime_profile["prompt_policy"] != self.prompt_policy:
            raise ValueError("VLM config/profile prompt policies differ")
        expected_temperature = (self.runtime_profile["sampling"]["temperature"]
                                if self.runtime_profile else 0.0)
        if getattr(args, "vlm_temperature", None) is None:
            args.vlm_temperature = expected_temperature
        elif self.runtime_profile and args.vlm_temperature != expected_temperature:
            raise ValueError("--vlm-temperature conflicts with the selected VLM production profile")
        runtime_options = image_cfg.get("runtime_options", {})
        # Explicit CLI settings take precedence; omitted values inherit the model config.
        for attribute, option, legacy_default in (
            ("vlm_ngl", "ngl", None),
            ("vlm_device", "device", ""),
            ("vlm_no_kv_offload", "no_kv_offload", False),
        ):
            if getattr(args, attribute, None) in (None, ""):
                setattr(args, attribute, runtime_options.get(option, legacy_default))
        if getattr(args, "vlm_no_mmproj_offload", None) is None:
            args.vlm_no_mmproj_offload = not runtime_options.get("mmproj_offload", True)
        for attribute, option, legacy_default in (
            ("vlm_ctx", "context", 2048),
            ("vlm_max_tokens", "max_output_tokens", 128),
            ("vlm_timeout_ms", "timeout_ms", 45000),
            ("vlm_image_min_tokens", "image_tokens", 1024),
            ("vlm_image_max_tokens", "image_tokens", 1024),
        ):
            if getattr(args, attribute, None) is None:
                setattr(args, attribute, image_cfg.get(option, legacy_default))
        self.output_path = output_path
        self.call_count = 0
        self.fallback_count = 0
        self.scheduler = image_cfg.get("scheduler", {})
        self.wake_alarm_types = {
            str(value) for value in (self.scheduler.get("wake_alarm_types") or []) if str(value)
        }
        self.wake_route_targets = {
            str(value) for value in (self.scheduler.get("wake_route_targets") or []) if str(value)
        }
        self.minimum_relationship_object_count = int(
            self.scheduler.get("minimum_relationship_object_count") or 2
        )
        self.minimum_interval_seconds = float(self.scheduler.get("minimum_interval_seconds") or 0.0)
        self.last_real_call_monotonic: float | None = None
        self.cooldown_skip_count = 0
        self.resource_gate_reject_count = 0
        self.route_skip_count = 0
        self.seen_request_keys: set[str] = set()
        self.once_prewarmed = False
        self.stub_worker = StubVlmWorker(image_cfg.get("model", "stub_vlm_worker"))
        self.resident_client: ResidentRkllmVlmClient | ResidentLlamaCppVlmClient | None = None
        if self.mode == "rkllm_multimodal_resident" and self.args.vlm_max_calls != 0:
            runner = self._resolve_resident_runner()
            runtime_log_dir = self.args.vlm_runtime_log_dir or (
                self.output_path.parent / f"{self.output_path.stem}_rkllm_vlm_resident_runtime"
            )
            runtime_log_path = runtime_log_dir / "rkllm_resident_vlm_server.log"
            self.resident_client = ResidentRkllmVlmClient(
                runner=runner,
                vision_model=str(self.args.vision_model),
                decoder_model=str(self.args.decoder_model),
                max_context_len=self.args.vlm_ctx,
                npu_core_num=self.args.npu_core_num,
                runtime_log_path=runtime_log_path,
                startup_timeout_sec=max(1.0, self.args.vlm_startup_timeout_ms / 1000.0),
                img_start=self.args.vlm_img_start,
                img_end=self.args.vlm_img_end,
                img_content=self.args.vlm_img_content,
                template_style=self.args.vlm_template_style,
            )
            self.resident_client.start()
        elif self.mode == "llama_cpp_multimodal_resident" and self.args.vlm_max_calls != 0:
            runtime_log_dir = self.args.vlm_runtime_log_dir or (
                self.output_path.parent / f"{self.output_path.stem}_llama_cpp_vlm_resident_runtime"
            )
            runtime_log_path = runtime_log_dir / "llama_cpp_resident_vlm_server.log"
            self.resident_client = self._build_llama_cpp_client(runtime_log_path)
            self.resident_client.start()

    def review(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        row = self._review(event, timestamp)
        row.setdefault("configured_vlm_prompt_policy", self.prompt_policy)
        row.setdefault("configured_vlm_runtime_profile",
                       self.runtime_profile["profile_id"] if self.runtime_profile else None)
        row.setdefault("vlm_input_mode", infer_vlm_input_mode(event))
        row.setdefault("context_crop_path", event.get("context_crop_path"))
        row.setdefault("context_crop_box", event.get("context_crop_box"))
        row.setdefault("context_detection_ids", event.get("context_detection_ids") or [])
        row.setdefault("evidence_frame_ids", event.get("evidence_frame_ids") or [])
        row.setdefault("keyframe_paths", event.get("keyframe_paths") or [])
        row.setdefault("temporal_contact_sheet_path", event.get("temporal_contact_sheet_path"))
        return row

    def _review(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        if self.mode == "stub":
            self.fallback_count += 1
            return self.stub_worker.review(event, timestamp)
        cooldown_remaining = self.cooldown_remaining_seconds()
        if cooldown_remaining > 0:
            self.fallback_count += 1
            self.cooldown_skip_count += 1
            row = self.stub_worker.review(event, timestamp)
            row["mode"] = f"{self.mode}_minimum_interval_stub_fallback"
            row["status"] = "not_executed"
            row["scheduler_decision"] = "cooldown_skip"
            row["minimum_interval_seconds"] = self.minimum_interval_seconds
            row["cooldown_remaining_seconds"] = round(cooldown_remaining, 3)
            return row
        if self.args.vlm_max_calls >= 0 and self.call_count >= self.args.vlm_max_calls:
            self.fallback_count += 1
            row = self.stub_worker.review(event, timestamp)
            row["mode"] = f"{self.mode}_budget_exhausted_stub_fallback"
            row["status"] = "not_executed"
            return row
        self.seen_request_keys.add(self.model_request_key(event))
        self.call_count += 1
        try:
            if self.mode == "rkllm_multimodal":
                return run_rkllm_multimodal(event, self.image_cfg, self._rkllm_multimodal_args())
            if self.mode == "rkllm_multimodal_resident":
                return self._run_rkllm_multimodal_resident(event, timestamp)
            if self.mode == "llama_cpp_multimodal_once":
                return self._run_llama_cpp_multimodal_once(event, timestamp)
            if self.mode == "llama_cpp_multimodal_resident":
                return self._run_llama_cpp_multimodal_resident(event, timestamp)
            raise ValueError(f"unsupported VLM worker mode: {self.mode}")
        finally:
            self.last_real_call_monotonic = time.monotonic()

    def cooldown_remaining_seconds(self) -> float:
        if self.last_real_call_monotonic is None or self.minimum_interval_seconds <= 0:
            return 0.0
        return max(0.0, self.minimum_interval_seconds - (time.monotonic() - self.last_real_call_monotonic))

    def resource_gate_fallback(
        self,
        event: dict[str, Any],
        timestamp: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        self.fallback_count += 1
        self.resource_gate_reject_count += 1
        row = self.stub_worker.review(event, timestamp)
        row["mode"] = f"{self.mode}_resource_gate_stub_fallback"
        row["status"] = "not_executed"
        row["scheduler_decision"] = "resource_gate_reject"
        row["resource_gate"] = decision
        return row

    def route_decision(self, event: dict[str, Any]) -> dict[str, Any]:
        alarm_type = str(event.get("alarm_type") or "")
        explicit_route = event.get("route_target")
        route_target = str(
            explicit_route
            or ("vlm_only" if alarm_type in self.wake_alarm_types else "rule_only")
        )
        if route_target not in self.wake_route_targets:
            return {
                "allowed": False,
                "reason": "route_target_does_not_require_vlm",
                "route_target": route_target,
                "alarm_type": alarm_type,
            }
        if self.wake_alarm_types and alarm_type not in self.wake_alarm_types:
            return {
                "allowed": False,
                "reason": "alarm_type_not_selected",
                "route_target": route_target,
                "alarm_type": alarm_type,
            }
        if event.get("vlm_purpose") == "relationship_review":
            detection_count = len(event.get("detections") or [])
            if detection_count < self.minimum_relationship_object_count:
                return {
                    "allowed": False,
                    "reason": "relationship_object_count_below_minimum",
                    "route_target": route_target,
                    "alarm_type": alarm_type,
                    "detection_count": detection_count,
                    "minimum_relationship_object_count": self.minimum_relationship_object_count,
                }
        request_key = self.model_request_key(event)
        if request_key in self.seen_request_keys:
            return {
                "allowed": False,
                "reason": "duplicate_model_request_key",
                "route_target": route_target,
                "alarm_type": alarm_type,
                "model_request_key": request_key,
            }
        return {
            "allowed": True,
            "reason": (
                "route_target_and_alarm_type_selected"
                if explicit_route
                else "legacy_event_inferred_vlm_only"
            ),
            "route_target": route_target,
            "alarm_type": alarm_type,
            "vlm_purpose": event.get("vlm_purpose"),
            "model_request_key": request_key,
        }

    def model_request_key(self, event: dict[str, Any]) -> str:
        return ":".join(
            [
                str(event.get("event_id") or "unknown_event"),
                str(event.get("alarm_revision") or 0),
                str(event.get("vlm_purpose") or "vlm_default"),
                str(event.get("evidence_hash") or "no_evidence_hash"),
            ]
        )

    def route_fallback(
        self,
        event: dict[str, Any],
        timestamp: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        self.route_skip_count += 1
        row = self.stub_worker.review(event, timestamp)
        row["mode"] = f"{self.mode}_route_skip_stub"
        row["status"] = "not_executed"
        row["scheduler_decision"] = "route_skip"
        row["route_decision"] = decision
        return row

    def should_prepare_assets(self) -> bool:
        if self.mode == "stub":
            return False
        if self.args.vlm_max_calls == 0:
            return False
        if self.args.vlm_max_calls >= 0 and self.call_count >= self.args.vlm_max_calls:
            return False
        if self.cooldown_remaining_seconds() > 0:
            return False
        return self.mode in {
            "rkllm_multimodal",
            "rkllm_multimodal_resident",
            "llama_cpp_multimodal_once",
            "llama_cpp_multimodal_resident",
        }

    def close(self) -> None:
        if self.resident_client is not None:
            self.resident_client.close()

    def runtime_info(self) -> dict[str, Any]:
        if self.mode == "llama_cpp_multimodal_once":
            server_bin = self._resolve_llama_server_bin()
            return {
                "mode": self.mode,
                "server_bin": str(server_bin),
                "ngl": self.args.vlm_ngl,
                "no_kv_offload": self.args.vlm_no_kv_offload,
                "mmproj_offload": not self.args.vlm_no_mmproj_offload,
                "request_retries": getattr(self.args, "vlm_request_retries", 0),
                "request_retry_backoff_sec": getattr(self.args, "vlm_retry_backoff_sec", 0.0),
                "once_prewarm_request": bool(getattr(self.args, "vlm_once_prewarm_request", False)),
                "once_prewarm_max_tokens": getattr(self.args, "vlm_once_prewarm_max_tokens", 0),
                "device": self.args.vlm_device or "auto",
                "mmproj_path": self.args.mmproj_path,
            }
        if self.resident_client is None:
            return {"mode": self.mode}
        if self.mode == "llama_cpp_multimodal_resident":
            server_bin = self._resolve_llama_server_bin()
            return {
                "mode": self.mode,
                "server_bin": str(server_bin),
                "server_pid": self.resident_client.server_pid,
                "model_load_count": self.resident_client.model_load_count,
                "request_count": self.resident_client.request_count,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "host": self.args.vlm_llama_server_host,
                "port": self.resident_client.port,
                "parallel": self.resident_client.parallel,
                "ngl": self.args.vlm_ngl,
                "no_kv_offload": self.args.vlm_no_kv_offload,
                "mmproj_offload": not self.args.vlm_no_mmproj_offload,
                "request_retries": getattr(self.args, "vlm_request_retries", 0),
                "request_retry_backoff_sec": getattr(self.args, "vlm_retry_backoff_sec", 0.0),
                "device": self.args.vlm_device or "auto",
                "mmproj_path": self.args.mmproj_path,
            }
        return {
            "mode": self.mode,
            "runner": str(self._resolve_resident_runner()),
            "server_pid": self.resident_client.server_pid,
            "model_load_count": self.resident_client.model_load_count,
            "request_count": self.resident_client.request_count,
            "runtime_log_path": str(self.resident_client.runtime_log_path),
        }

    def _rkllm_multimodal_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            rkllm_mm_wrapper=self.args.rkllm_mm_wrapper,
            rkllm_mm_runner=self.args.rkllm_mm_runner,
            vision_model=self.args.vision_model,
            decoder_model=self.args.decoder_model,
            metrics_dir=self.args.vlm_metrics_dir,
            runtime_log_dir=self.args.vlm_runtime_log_dir,
            ctx=self.args.vlm_ctx,
            max_tokens=self.args.vlm_max_tokens,
            npu_core_num=self.args.npu_core_num,
            img_start=self.args.vlm_img_start,
            img_end=self.args.vlm_img_end,
            img_content=self.args.vlm_img_content,
            template_style=self.args.vlm_template_style,
            timeout_ms=self.args.vlm_timeout_ms,
            output=self.output_path,
        )

    def _resolve_resident_runner(self) -> Path:
        if self.args.rkllm_mm_resident_runner:
            return Path(self.args.rkllm_mm_resident_runner)
        candidates = [
            Path("projects/05_alarm_system/runners/rkllm_resident_vlm_server/build/rkllm_resident_vlm_server"),
            Path("build/05_alarm_system_rkllm_vlm/rkllm_resident_vlm_server"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _resolve_llama_server_bin(self) -> Path:
        if getattr(self.args, "vlm_llama_server_bin", ""):
            return Path(self.args.vlm_llama_server_bin)
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

    def _build_llama_cpp_client(self, runtime_log_path: Path) -> ResidentLlamaCppVlmClient:
        server_bin = self._resolve_llama_server_bin()
        return ResidentLlamaCppVlmClient(
            server_bin=server_bin,
            model_path=self.args.vlm_model_path,
            mmproj_path=self.args.mmproj_path,
            max_context_len=self.args.vlm_ctx,
            runtime_log_path=runtime_log_path,
            startup_timeout_sec=max(1.0, self.args.vlm_startup_timeout_ms / 1000.0),
            host=self.args.vlm_llama_server_host,
            port=self.args.vlm_llama_server_port,
            ngl=self.args.vlm_ngl,
            parallel=1,
            temperature=self.args.vlm_temperature,
            jinja=not self.args.vlm_llama_server_no_jinja,
            image_min_tokens=self.args.vlm_image_min_tokens,
            image_max_tokens=self.args.vlm_image_max_tokens,
            mmproj_offload=not self.args.vlm_no_mmproj_offload,
            no_kv_offload=self.args.vlm_no_kv_offload,
            device=self.args.vlm_device,
            threads=self.image_cfg.get("runtime_options", {}).get("threads"),
            threads_batch=self.image_cfg.get("runtime_options", {}).get("threads_batch"),
            sampling=self.runtime_profile["sampling"] if self.runtime_profile else None,
            seed=self.runtime_profile["seed"] if self.runtime_profile else None,
            cache_prompt=self.runtime_profile["cache_prompt"] if self.runtime_profile else None,
            cache_ram_mib=self.runtime_profile["cache_ram_mib"] if self.runtime_profile else None,
            cpu_kernel=self.runtime_profile.get("cpu_kernel") if self.runtime_profile else None,
        )

    def _run_rkllm_multimodal_resident(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        assert self.resident_client is not None
        image_path, image_source = select_image_path(event)
        if image_path is None:
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "rkllm_multimodal_resident_service_worker",
                "vlm_summary": None,
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": None,
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": None,
                "vlm_total_ms": None,
                "decode_tokens_per_s": None,
                "prompt_tokens": None,
                "output_tokens": None,
                "metrics_json_path": None,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "status": "blocked_no_image_asset",
            }
        prompt = build_prompt(event)
        try:
            response = self.resident_client.request(
                request_id=str(event["event_id"]),
                image_path=str(image_path),
                prompt=prompt,
                max_output_tokens=self.args.vlm_max_tokens,
                timeout_sec=max(1.0, self.args.vlm_timeout_ms / 1000.0),
            )
            summary = response.get("output_text") or ""
            status = "pass" if response.get("status") == "ok" and summary else "failed"
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "rkllm_multimodal_resident_service_worker",
                "vlm_summary": summary or None,
                "vlm_raw_output": summary or None,
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": str(image_path),
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": response.get("image_preprocess_time_ms"),
                "vlm_total_ms": response.get("total_time_ms"),
                "decode_tokens_per_s": response.get("decode_tokens_per_s"),
                "prompt_tokens": response.get("prompt_tokens"),
                "output_tokens": response.get("output_tokens"),
                "metrics_json_path": None,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "exit_code": response.get("exit_code"),
                "metrics_status": response.get("status"),
                "metrics_error": response.get("error"),
                "resident_server_pid": response.get("pid"),
                "resident_model_load_count": response.get("model_load_count"),
                "resident_request_index": response.get("request_index"),
                "status": status,
            }
        except Exception as exc:
            self.fallback_count += 1
            row = self.stub_worker.review(event, timestamp)
            row["mode"] = "rkllm_multimodal_resident_request_failed_stub_fallback"
            row["status"] = "fallback"
            row["image_path"] = str(image_path)
            row["image_source_field"] = image_source
            row["metrics_error"] = str(exc)
            row["runtime_log_path"] = str(self.resident_client.runtime_log_path)
            return row

    def _run_llama_cpp_multimodal_resident(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        assert self.resident_client is not None
        image_path, image_source = select_image_path(event)
        if image_path is None:
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "llama_cpp_multimodal_resident_service_worker",
                "vlm_summary": None,
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": None,
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": None,
                "vlm_total_ms": None,
                "decode_tokens_per_s": None,
                "prompt_tokens": None,
                "output_tokens": None,
                "metrics_json_path": None,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "status": "blocked_no_image_asset",
            }
        prompt = build_prompt(event)
        try:
            response, retry_count = self._request_llama_cpp_resident_with_retries(
                request_id=str(event["event_id"]),
                image_path=str(image_path),
                prompt=prompt,
            )
            summary = response.get("output_text") or ""
            status = "pass" if response.get("status") == "ok" and summary else "failed"
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "llama_cpp_multimodal_resident_service_worker",
                "vlm_summary": summary or None,
                "vlm_raw_output": summary or None,
                "vlm_prompt_sha256": response.get("request_prompt_sha256"),
                "vlm_requested_sampling": response.get("requested_sampling"),
                "vlm_requested_seed": response.get("requested_seed"),
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": str(image_path),
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": None,
                "vlm_total_ms": response.get("total_time_ms"),
                "decode_tokens_per_s": response.get("decode_tokens_per_s"),
                "prompt_tokens": response.get("prompt_tokens"),
                "output_tokens": response.get("output_tokens"),
                "metrics_json_path": None,
                "runtime_log_path": str(self.resident_client.runtime_log_path),
                "exit_code": response.get("exit_code"),
                "metrics_status": response.get("status"),
                "metrics_error": response.get("error"),
                "resident_retry_count": retry_count,
                "prefill_ms": response.get("prefill_ms"),
                "decode_ms": response.get("decode_ms"),
                "finish_reason": response.get("finish_reason"),
                "resident_server_pid": response.get("pid"),
                "resident_model_load_count": response.get("model_load_count"),
                "resident_request_index": response.get("request_index"),
                "status": status,
            }
        except Exception as exc:
            self.fallback_count += 1
            row = self.stub_worker.review(event, timestamp)
            row["mode"] = "llama_cpp_multimodal_resident_request_failed_stub_fallback"
            row["status"] = "fallback"
            row["image_path"] = str(image_path)
            row["image_source_field"] = image_source
            row["metrics_error"] = str(exc)
            row["runtime_log_path"] = str(self.resident_client.runtime_log_path)
            return row

    def _run_llama_cpp_multimodal_once(self, event: dict[str, Any], timestamp: str) -> dict[str, Any]:
        image_path, image_source = select_image_path(event)
        runtime_log_dir = self.args.vlm_runtime_log_dir or (
            self.output_path.parent / f"{self.output_path.stem}_llama_cpp_vlm_once_runtime"
        )
        runtime_log_path = runtime_log_dir / f"{safe_name(str(event['event_id']))}.log"
        if image_path is None:
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "llama_cpp_multimodal_once_service_worker",
                "vlm_summary": None,
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": None,
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": None,
                "vlm_total_ms": None,
                "decode_tokens_per_s": None,
                "prompt_tokens": None,
                "output_tokens": None,
                "metrics_json_path": None,
                "runtime_log_path": str(runtime_log_path),
                "status": "blocked_no_image_asset",
            }
        prompt = build_prompt(event)
        last_runtime_log_path = runtime_log_path
        try:
            if self._should_run_once_prewarm():
                self._run_llama_cpp_once_prewarm(
                    event_id=str(event["event_id"]),
                    image_path=str(image_path),
                    prompt=prompt,
                    runtime_log_path=runtime_log_path,
                )
            response, retry_count, last_runtime_log_path = self._request_llama_cpp_once_with_retries(
                request_id=str(event["event_id"]),
                image_path=str(image_path),
                prompt=prompt,
                runtime_log_path=runtime_log_path,
            )
            summary = response.get("output_text") or ""
            status = "pass" if response.get("status") == "ok" and summary else "failed"
            return {
                "event_id": event["event_id"],
                "timestamp": timestamp,
                "model": self.image_cfg.get("model", "unknown_vlm"),
                "mode": "llama_cpp_multimodal_once_service_worker",
                "vlm_summary": summary or None,
                "vlm_raw_output": summary or None,
                "vlm_prompt_sha256": response.get("request_prompt_sha256"),
                "vlm_requested_sampling": response.get("requested_sampling"),
                "vlm_requested_seed": response.get("requested_seed"),
                "roi_count": len(event.get("roi_boxes") or []),
                "image_path": str(image_path),
                "image_source_field": image_source,
                "timeout_ms": self.args.vlm_timeout_ms,
                "image_preprocess_ms": None,
                "vlm_total_ms": response.get("total_time_ms"),
                "decode_tokens_per_s": response.get("decode_tokens_per_s"),
                "prompt_tokens": response.get("prompt_tokens"),
                "output_tokens": response.get("output_tokens"),
                "metrics_json_path": None,
                "runtime_log_path": str(last_runtime_log_path),
                "exit_code": response.get("exit_code"),
                "metrics_status": response.get("status"),
                "metrics_error": response.get("error"),
                "resident_retry_count": retry_count,
                "resident_server_pid": response.get("pid"),
                "resident_model_load_count": response.get("model_load_count"),
                "resident_request_index": response.get("request_index"),
                "status": status,
            }
        except Exception as exc:
            self.fallback_count += 1
            row = self.stub_worker.review(event, timestamp)
            row["mode"] = "llama_cpp_multimodal_once_request_failed_stub_fallback"
            row["status"] = "fallback"
            row["image_path"] = str(image_path)
            row["image_source_field"] = image_source
            row["metrics_error"] = str(exc)
            row["runtime_log_path"] = str(last_runtime_log_path)
            return row

    def _request_llama_cpp_resident_with_retries(
        self,
        *,
        request_id: str,
        image_path: str,
        prompt: str,
    ) -> tuple[dict[str, Any], int]:
        assert self.resident_client is not None
        max_retries = max(0, int(getattr(self.args, "vlm_request_retries", 0)))
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self.resident_client.request(
                    request_id=request_id,
                    image_path=image_path,
                    prompt=prompt,
                    max_output_tokens=self.args.vlm_max_tokens,
                    timeout_sec=max(1.0, self.args.vlm_timeout_ms / 1000.0),
                )
                return response, attempt
            except Exception as exc:
                last_exc = exc
                if attempt >= max_retries:
                    break
                backoff_sec = self._retry_backoff_sec()
                if backoff_sec > 0:
                    time.sleep(backoff_sec)
                self._restart_llama_cpp_resident_client()
        assert last_exc is not None
        raise last_exc

    def _request_llama_cpp_once_with_retries(
        self,
        *,
        request_id: str,
        image_path: str,
        prompt: str,
        runtime_log_path: Path,
        max_output_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any], int, Path]:
        max_retries = max(0, int(getattr(self.args, "vlm_request_retries", 0)))
        last_exc: Exception | None = None
        last_runtime_log_path = runtime_log_path
        for attempt in range(max_retries + 1):
            current_runtime_log_path = runtime_log_path
            if attempt > 0:
                current_runtime_log_path = runtime_log_path.with_name(
                    f"{runtime_log_path.stem}_retry{attempt}{runtime_log_path.suffix}"
                )
            last_runtime_log_path = current_runtime_log_path
            client = self._build_llama_cpp_client(current_runtime_log_path)
            try:
                client.start()
                response = client.request(
                    request_id=request_id,
                    image_path=image_path,
                    prompt=prompt,
                    max_output_tokens=(
                        max_output_tokens_override
                        if max_output_tokens_override is not None
                        else self.args.vlm_max_tokens
                    ),
                    timeout_sec=max(1.0, self.args.vlm_timeout_ms / 1000.0),
                )
                return response, attempt, current_runtime_log_path
            except Exception as exc:
                last_exc = exc
            finally:
                client.close(force=True)
            if attempt < max_retries:
                backoff_sec = self._retry_backoff_sec()
                if backoff_sec > 0:
                    time.sleep(backoff_sec)
        assert last_exc is not None
        raise RuntimeError(
            f"{last_exc}; once_attempts={max_retries + 1}; last_runtime_log={last_runtime_log_path}"
        ) from last_exc

    def _restart_llama_cpp_resident_client(self) -> None:
        assert self.resident_client is not None
        self.resident_client.close(force=True)
        self.resident_client.start()

    def _retry_backoff_sec(self) -> float:
        raw = getattr(self.args, "vlm_retry_backoff_sec", 0.0)
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return 0.0

    def _should_run_once_prewarm(self) -> bool:
        if self.mode != "llama_cpp_multimodal_once":
            return False
        if self.once_prewarmed:
            return False
        return bool(getattr(self.args, "vlm_once_prewarm_request", False))

    def _run_llama_cpp_once_prewarm(
        self,
        *,
        event_id: str,
        image_path: str,
        prompt: str,
        runtime_log_path: Path,
    ) -> None:
        prewarm_tokens = self._once_prewarm_max_tokens()
        if prewarm_tokens <= 0:
            self.once_prewarmed = True
            return

        prewarm_log_path = runtime_log_path.with_name(
            f"{runtime_log_path.stem}_prewarm{runtime_log_path.suffix}"
        )
        try:
            self._request_llama_cpp_once_with_retries(
                request_id=f"{event_id}__prewarm",
                image_path=image_path,
                prompt=prompt,
                runtime_log_path=prewarm_log_path,
                max_output_tokens_override=prewarm_tokens,
            )
        except Exception:
            # Prewarm is best-effort. The real counted request still decides pass/fail.
            pass
        finally:
            self.once_prewarmed = True

    def _once_prewarm_max_tokens(self) -> int:
        raw = getattr(self.args, "vlm_once_prewarm_max_tokens", 0)
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0
