#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class ResidentRkllmVlmClient:
    def __init__(
        self,
        *,
        runner: Path,
        vision_model: str,
        decoder_model: str,
        max_context_len: int,
        npu_core_num: int,
        runtime_log_path: Path,
        startup_timeout_sec: float = 30.0,
        img_start: str = "<|vision_start|>",
        img_end: str = "<|vision_end|>",
        img_content: str = "<|image_pad|>",
        template_style: str = "qwen",
        taskset_mask: str = "",
    ) -> None:
        self.runner = Path(runner)
        self.vision_model = vision_model
        self.decoder_model = decoder_model
        self.max_context_len = max_context_len
        self.npu_core_num = npu_core_num
        self.runtime_log_path = runtime_log_path
        self.startup_timeout_sec = startup_timeout_sec
        self.img_start = img_start
        self.img_end = img_end
        self.img_content = img_content
        self.template_style = template_style
        self.taskset_mask = taskset_mask.strip()
        self.process: subprocess.Popen[str] | None = None
        self.stdout_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader_thread: threading.Thread | None = None
        self.runtime_log_handle = None
        self.request_count = 0
        self.model_load_count = 0
        self.server_pid: int | None = None
        self.ready_payload: dict[str, Any] | None = None

    def _command(self) -> list[str]:
        command: list[str] = []
        if self.taskset_mask:
            command.extend(["taskset", self.taskset_mask])
        command.extend(
            [
                str(self.runner),
                "--vision-model",
                self.vision_model,
                "--decoder-model",
                self.decoder_model,
                "--max-context-len",
                str(self.max_context_len),
                "--npu-core-num",
                str(self.npu_core_num),
                "--img-start",
                self.img_start,
                "--img-end",
                self.img_end,
                "--img-content",
                self.img_content,
                "--template-style",
                self.template_style,
            ]
        )
        return command

    def _reader_loop(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        for raw_line in self.process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"type": "protocol_error", "status": "error", "raw_line": line}
            self.stdout_queue.put(payload)

    def start(self) -> dict[str, Any]:
        if not self.runner.exists():
            raise FileNotFoundError(f"resident RKLLM VLM runner not found: {self.runner}")
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_log_handle = self.runtime_log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.runtime_log_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=(os.name == "posix"),
        )
        self.reader_thread = threading.Thread(target=self._reader_loop, name="rkllm-resident-vlm-reader", daemon=True)
        self.reader_thread.start()
        deadline = time.monotonic() + self.startup_timeout_sec
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"resident RKLLM VLM server exited during startup: exit_code={self.process.returncode}, "
                    f"runtime_log={self.runtime_log_path}"
                )
            try:
                payload = self.stdout_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if payload.get("type") != "ready":
                continue
            if payload.get("status") != "ok":
                raise RuntimeError(
                    f"resident RKLLM VLM server startup failed: {payload.get('error')}, "
                    f"runtime_log={self.runtime_log_path}"
                )
            self.ready_payload = payload
            self.model_load_count = int(payload.get("model_load_count") or 0)
            self.server_pid = int(payload.get("pid") or 0) or self.process.pid
            return payload
        self.close(force=True)
        raise TimeoutError(f"resident RKLLM VLM server ready timeout: {self.runtime_log_path}")

    def request(
        self,
        *,
        request_id: str,
        image_path: str,
        prompt: str,
        max_output_tokens: int,
        timeout_sec: float,
    ) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("resident RKLLM VLM server is not running")
        if self.process.poll() is not None:
            raise RuntimeError(
                f"resident RKLLM VLM server already exited: exit_code={self.process.returncode}, "
                f"runtime_log={self.runtime_log_path}"
            )
        payload = {
            "request_id": request_id,
            "image_path": image_path,
            "prompt": prompt,
            "max_output_tokens": max_output_tokens,
        }
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"resident RKLLM VLM server exited mid-request: exit_code={self.process.returncode}, "
                    f"runtime_log={self.runtime_log_path}"
                )
            try:
                response = self.stdout_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if response.get("type") != "response":
                continue
            if response.get("request_id") not in {"", request_id}:
                continue
            self.request_count += 1
            return response
        self.close(force=True)
        raise TimeoutError(
            f"resident RKLLM VLM request timeout: request_id={request_id}, runtime_log={self.runtime_log_path}"
        )

    def close(self, force: bool = False) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            if not force and process.stdin is not None:
                try:
                    process.stdin.write('{"command":"shutdown"}\n')
                    process.stdin.flush()
                    process.wait(timeout=3.0)
                except Exception:
                    force = True
            if force and process.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
                    process.wait(timeout=3.0)
                except Exception:
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except Exception:
                        pass
        if self.runtime_log_handle is not None:
            self.runtime_log_handle.close()
            self.runtime_log_handle = None
        self.process = None
