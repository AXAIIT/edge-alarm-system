#!/usr/bin/env python3
from __future__ import annotations

import base64
import copy
import hashlib
import json
import mimetypes
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from vlm_runtime_profile import SAMPLING_KEYS, kernel_startup, verify_kernel_loaded


class ResidentLlamaCppVlmClient:
    def __init__(
        self,
        *,
        server_bin: Path,
        model_path: str,
        mmproj_path: str,
        max_context_len: int,
        runtime_log_path: Path,
        startup_timeout_sec: float = 30.0,
        host: str = "127.0.0.1",
        port: int = 0,
        ngl: int | None = None,
        parallel: int = 1,
        temperature: float = 0.0,
        jinja: bool = True,
        image_min_tokens: int | None = None,
        image_max_tokens: int | None = None,
        mmproj_offload: bool = True,
        no_kv_offload: bool = False,
        device: str = "",
        threads: int | None = None,
        threads_batch: int | None = None,
        sampling: dict[str, Any] | None = None,
        seed: int | None = None,
        cache_prompt: bool | None = None,
        cache_ram_mib: int | None = None,
        cpu_kernel: dict[str, Any] | None = None,
    ) -> None:
        self.server_bin = Path(server_bin)
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.max_context_len = max_context_len
        self.runtime_log_path = runtime_log_path
        self.startup_timeout_sec = startup_timeout_sec
        self.host = host
        self.requested_port = int(port)
        self.port = int(port)
        self.ngl = ngl
        self.parallel = max(1, int(parallel))
        self.temperature = temperature
        self.jinja = jinja
        self.image_min_tokens = image_min_tokens
        self.image_max_tokens = image_max_tokens
        self.mmproj_offload = mmproj_offload
        self.no_kv_offload = no_kv_offload
        self.device = device
        self.threads = threads
        self.threads_batch = threads_batch
        if sampling is not None and set(sampling) != SAMPLING_KEYS:
            raise ValueError("VLM sampling fields incomplete or unknown")
        if sampling is not None and float(sampling["temperature"]) != float(temperature):
            raise ValueError("VLM command/request temperatures differ")
        self.sampling = copy.deepcopy(sampling)
        self.seed = seed
        self.cache_prompt = cache_prompt
        if cache_ram_mib is not None and (type(cache_ram_mib) is not int or cache_ram_mib < 0):
            raise ValueError("VLM extra prompt-cache pool must be a nonnegative MiB limit")
        self.cache_ram_mib = cache_ram_mib
        self.cpu_kernel = cpu_kernel
        self.process: subprocess.Popen[str] | None = None
        self.runtime_log_handle = None
        self.request_count = 0
        self.model_load_count = 0
        self.server_pid: int | None = None

    def _pick_port(self) -> int:
        if self.requested_port > 0:
            return self.requested_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((self.host, 0))
            sock.listen(1)
            return int(sock.getsockname()[1])

    def _command(self) -> list[str]:
        device = self.device.strip()
        if device.lower() == "cpu":
            device = "none"
        elif device.lower() == "auto":
            # This pinned llama.cpp accepts device names/none, not the literal "auto".
            # Omitting --device retains backend auto-discovery for the visual module.
            device = ""
        command = [
            str(self.server_bin),
            "-m",
            self.model_path,
            "--mmproj",
            self.mmproj_path,
            "-c",
            str(self.max_context_len),
            "--temp",
            str(self.temperature),
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        if self.ngl is not None:
            command.extend(["-ngl", str(self.ngl)])
        command.extend(["-np", str(self.parallel)])
        if self.image_min_tokens is not None:
            command.extend(["--image-min-tokens", str(self.image_min_tokens)])
        if self.image_max_tokens is not None:
            command.extend(["--image-max-tokens", str(self.image_max_tokens)])
        command.append("--mmproj-offload" if self.mmproj_offload else "--no-mmproj-offload")
        if self.no_kv_offload:
            command.append("--no-kv-offload")
        if device:
            command.extend(["--device", device])
        if self.threads is not None:
            command.extend(["--threads", str(self.threads)])
        if self.threads_batch is not None:
            command.extend(["--threads-batch", str(self.threads_batch)])
        if self.cache_ram_mib is not None:
            command.extend(["--cache-ram", str(self.cache_ram_mib)])
        if self.jinja:
            command.append("--jinja")
        return command

    def _health_urls(self) -> list[str]:
        base = f"http://{self.host}:{self.port}"
        return [f"{base}/health", f"{base}/v1/health"]

    def _chat_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1/chat/completions"

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout_sec
        while time.monotonic() < deadline:
            if self.process is None:
                break
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"resident llama.cpp VLM server exited during startup: exit_code={self.process.returncode}, "
                    f"runtime_log={self.runtime_log_path}"
                )
            ready = False
            for health_url in self._health_urls():
                try:
                    request = urllib.request.Request(health_url, method="GET")
                    with urllib.request.urlopen(request, timeout=1.0) as response:
                        if response.status == 200:
                            ready = True
                            break
                except urllib.error.HTTPError as exc:
                    if exc.code == 503:
                        continue
                except Exception:
                    continue
            if ready:
                return
            time.sleep(0.2)
        self.close(force=True)
        raise TimeoutError(f"resident llama.cpp VLM server ready timeout: {self.runtime_log_path}")

    def start(self) -> dict[str, Any]:
        if not self.server_bin.exists():
            raise FileNotFoundError(f"resident llama.cpp VLM server not found: {self.server_bin}")
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"resident llama.cpp VLM model not found: {self.model_path}")
        if not Path(self.mmproj_path).exists():
            raise FileNotFoundError(f"resident llama.cpp VLM mmproj not found: {self.mmproj_path}")
        child_environment, libraries = (kernel_startup(
            self.cpu_kernel, self.server_bin, Path(self.model_path), Path(self.mmproj_path))
            if self.cpu_kernel else (None, []))
        self.port = self._pick_port()
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_log_handle = self.runtime_log_path.open("w", encoding="utf-8")
        loaded_libraries = {}
        try:
            self.process = subprocess.Popen(
                self._command(),
                stdin=subprocess.DEVNULL,
                stdout=self.runtime_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=(os.name == "posix"),
                env=child_environment,
            )
            self._wait_until_ready()
            if libraries:
                loaded_libraries = verify_kernel_loaded(libraries, self.process.pid)
                self.runtime_log_handle.write(json.dumps({"vlm_cpu_kernel": self.cpu_kernel["policy"],
                                                          "loaded_libraries": loaded_libraries}) + "\n")
                self.runtime_log_handle.flush()
        except Exception:
            self.close(force=True)
            raise
        self.server_pid = self.process.pid
        self.model_load_count = 1
        return {
            "status": "ok",
            "pid": self.server_pid,
            "model_load_count": self.model_load_count,
            "host": self.host,
            "port": self.port,
            "loaded_libraries": loaded_libraries,
        }

    def _image_data_url(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"resident llama.cpp VLM image not found: {image_path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{data}"

    def request(
        self,
        *,
        request_id: str,
        image_path: str,
        prompt: str,
        max_output_tokens: int,
        timeout_sec: float,
    ) -> dict[str, Any]:
        if self.process is None:
            raise RuntimeError("resident llama.cpp VLM server is not running")
        if self.process.poll() is not None:
            raise RuntimeError(
                f"resident llama.cpp VLM server already exited: exit_code={self.process.returncode}, "
                f"runtime_log={self.runtime_log_path}"
            )
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": self._image_data_url(image_path)}},
                    ],
                }
            ],
            "temperature": self.temperature,
            "max_tokens": max_output_tokens,
        }
        if self.sampling is not None:
            payload.update(copy.deepcopy(self.sampling))
        if self.seed is not None:
            payload["seed"] = self.seed
        if self.cache_prompt is not None:
            payload["cache_prompt"] = self.cache_prompt
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._chat_url(),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"resident llama.cpp VLM HTTP error: status={exc.code}, body={body[:400]}, "
                f"runtime_log={self.runtime_log_path}"
            ) from exc
        except Exception as exc:
            self.close(force=True)
            raise RuntimeError(
                f"resident llama.cpp VLM request failed: {type(exc).__name__}: {exc}, "
                f"runtime_log={self.runtime_log_path}"
            ) from exc
        total_ms = round((time.monotonic() - start) * 1000.0, 3)
        usage = parsed.get("usage", {}) if isinstance(parsed, dict) else {}
        timings = parsed.get("timings", {}) if isinstance(parsed, dict) else {}
        content = (
            parsed.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            if isinstance(parsed, dict)
            else ""
        ) or ""
        self.request_count += 1
        return {
            "type": "response",
            "status": "ok",
            "request_id": request_id,
            "output_text": content,
            "prompt_tokens": usage.get("prompt_tokens") or timings.get("prompt_n"),
            "output_tokens": usage.get("completion_tokens") or timings.get("predicted_n"),
            "first_token_ms": None,
            "prefill_ms": timings.get("prompt_ms"),
            "decode_ms": timings.get("predicted_ms"),
            "finish_reason": (parsed.get("choices") or [{}])[0].get("finish_reason"),
            "decode_tokens_per_s": timings.get("predicted_per_second"),
            "total_time_ms": total_ms,
            "pid": self.server_pid,
            "model_load_count": self.model_load_count,
            "request_index": self.request_count,
            "request_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "requested_sampling": copy.deepcopy(self.sampling),
            "requested_seed": self.seed,
            "requested_cache_prompt": self.cache_prompt,
            "exit_code": 0,
        }

    def close(self, force: bool = False) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=3.0)
            except Exception:
                if force or process.poll() is None:
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
