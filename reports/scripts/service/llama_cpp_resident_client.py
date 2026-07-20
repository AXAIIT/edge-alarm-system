#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class ResidentLlamaCppTextClient:
    def __init__(
        self,
        *,
        server_bin: Path,
        model_path: str,
        max_context_len: int,
        runtime_log_path: Path,
        startup_timeout_sec: float = 30.0,
        host: str = "127.0.0.1",
        port: int = 0,
        ngl: int | None = None,
        parallel: int = 1,
        temperature: float = 0.0,
        jinja: bool = True,
        no_kv_offload: bool = False,
        device: str = "",
    ) -> None:
        self.server_bin = Path(server_bin)
        self.model_path = model_path
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
        self.no_kv_offload = no_kv_offload
        self.device = device
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
        command = [
            str(self.server_bin),
            "-m",
            self.model_path,
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
        if self.no_kv_offload:
            command.append("--no-kv-offload")
        if device:
            command.extend(["--device", device])
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
                    f"resident llama.cpp server exited during startup: exit_code={self.process.returncode}, "
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
        raise TimeoutError(f"resident llama.cpp server ready timeout: {self.runtime_log_path}")

    def start(self) -> dict[str, Any]:
        if not self.server_bin.exists():
            raise FileNotFoundError(f"resident llama.cpp server not found: {self.server_bin}")
        self.port = self._pick_port()
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_log_handle = self.runtime_log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            self._command(),
            stdin=subprocess.DEVNULL,
            stdout=self.runtime_log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name == "posix"),
        )
        self._wait_until_ready()
        self.server_pid = self.process.pid
        self.model_load_count = 1
        return {
            "status": "ok",
            "pid": self.server_pid,
            "model_load_count": self.model_load_count,
            "host": self.host,
            "port": self.port,
        }

    def request(self, *, request_id: str, prompt: str, max_output_tokens: int, timeout_sec: float) -> dict[str, Any]:
        if self.process is None:
            raise RuntimeError("resident llama.cpp server is not running")
        if self.process.poll() is not None:
            raise RuntimeError(
                f"resident llama.cpp server already exited: exit_code={self.process.returncode}, "
                f"runtime_log={self.runtime_log_path}"
            )
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": max_output_tokens,
        }
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
                f"resident llama.cpp HTTP error: status={exc.code}, body={body[:400]}, "
                f"runtime_log={self.runtime_log_path}"
            ) from exc
        except Exception as exc:
            self.close(force=True)
            raise RuntimeError(
                f"resident llama.cpp request failed: {type(exc).__name__}: {exc}, "
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
            "decode_tokens_per_s": timings.get("predicted_per_second"),
            "total_time_ms": total_ms,
            "pid": self.server_pid,
            "model_load_count": self.model_load_count,
            "request_index": self.request_count,
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
