#!/usr/bin/env python3
"""Run or control the RK3588 Project5 P3 smoke process."""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_SCRIPT = REPO_ROOT / "projects/05_alarm_system/scripts/service/run_rk3588_p3_resident_detector_smoke.sh"


def runtime_paths(run_id: str) -> tuple[Path, Path, Path]:
    root = REPO_ROOT / "logs/runtime/05_alarm_system/rk3588_8gb"
    return (
        root / f"{run_id}_p3_launcher.pid",
        root / f"{run_id}_p3_launcher.log",
        root / f"{run_id}_p3_status.env",
    )


def read_pid(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return int(value)
    except (OSError, ValueError):
        return None


def is_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_status(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line)


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "RUN_ID": args.run_id,
            "BOARD": "rk3588_8gb",
            "ENV_BASELINE_ID": args.environment_baseline_id,
            "DURATION_SEC": str(args.duration_sec),
        }
    )
    return env


def print_status_file(path: Path) -> None:
    status_values = read_status(path)
    for key in sorted(status_values):
        print(f"{key}={status_values[key]}")


def print_launcher_tail(path: Path, limit: int = 40) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        print(f"launcher_log_missing={path.relative_to(REPO_ROOT)}")
        return
    print("launcher_log_tail_begin")
    for line in lines[-limit:]:
        print(line)
    print("launcher_log_tail_end")


def clear_runtime_files(pid_path: Path, status_path: Path) -> None:
    for path in (pid_path, status_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def wait_startup(process: subprocess.Popen[str], status_path: Path, timeout_sec: float) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if status_path.exists():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    return status_path.exists()


def start(args: argparse.Namespace) -> int:
    pid_path, launcher_log, status_path = runtime_paths(args.run_id)
    active_pid = read_pid(pid_path)
    if is_running(active_pid):
        print(f"P3 already running: pid={active_pid} run_id={args.run_id}")
        return 2
    if not RUN_SCRIPT.is_file():
        print(f"missing Project5 P3 runner: {RUN_SCRIPT}", file=sys.stderr)
        return 2

    launcher_log.parent.mkdir(parents=True, exist_ok=True)
    clear_runtime_files(pid_path, status_path)
    env = build_env(args)
    with launcher_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["bash", str(RUN_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
    started = wait_startup(process, status_path, args.startup_wait_sec)
    if not started and process.poll() is not None:
        print(f"P3 exited during startup: exit_code={process.returncode}", file=sys.stderr)
        print(f"launcher_log={launcher_log.relative_to(REPO_ROOT)}", file=sys.stderr)
        print_launcher_tail(launcher_log)
        return process.returncode or 1
    print(f"P3 launched: pid={process.pid}")
    print(f"launcher_log={launcher_log.relative_to(REPO_ROOT)}")
    print(f"status_file={status_path.relative_to(REPO_ROOT)}")
    if status_path.exists():
        print_status_file(status_path)
    return 0


def status(args: argparse.Namespace) -> int:
    pid_path, launcher_log, status_path = runtime_paths(args.run_id)
    pid = read_pid(pid_path)
    print(f"run_id={args.run_id}")
    print(f"pid={pid}")
    print(f"process_running={is_running(pid)}")
    print(f"launcher_log={launcher_log.relative_to(REPO_ROOT)}")
    status_values = read_status(status_path)
    for key in sorted(status_values):
        print(f"{key}={status_values[key]}")
    if not status_values:
        print("state=not_started_or_status_not_written")
        if launcher_log.exists():
            print_launcher_tail(launcher_log, limit=20)
    return 0


def stop(args: argparse.Namespace) -> int:
    pid_path, _, _ = runtime_paths(args.run_id)
    pid = read_pid(pid_path)
    if not is_running(pid):
        print(f"P3 is not running: run_id={args.run_id}")
        return 0
    assert pid is not None
    os.killpg(pid, signal.SIGTERM)
    print(f"P3 termination requested for process group {pid}")
    return 0


def run(args: argparse.Namespace) -> int:
    pid_path, launcher_log, status_path = runtime_paths(args.run_id)
    active_pid = read_pid(pid_path)
    if is_running(active_pid):
        print(f"P3 already running: pid={active_pid} run_id={args.run_id}")
        return 2
    if not RUN_SCRIPT.is_file():
        print(f"missing Project5 P3 runner: {RUN_SCRIPT}", file=sys.stderr)
        return 2

    launcher_log.parent.mkdir(parents=True, exist_ok=True)
    clear_runtime_files(pid_path, status_path)
    env = build_env(args)
    print(f"foreground_run={RUN_SCRIPT.relative_to(REPO_ROOT)}")
    print(f"run_id={args.run_id}")
    print(f"status_file={status_path.relative_to(REPO_ROOT)}")
    print(f"launcher_log={launcher_log.relative_to(REPO_ROOT)}")
    with launcher_log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["bash", str(RUN_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            output.write(line)
            output.flush()
    exit_code = process.wait()
    print(f"foreground_exit_code={exit_code}")
    if status_path.exists():
        print_status_file(status_path)
    else:
        print("state=not_started_or_status_not_written")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "run", "status", "stop"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--run-id", required=True)
        if command in ("start", "run"):
            subparser.add_argument("--duration-sec", type=int, default=600)
            subparser.add_argument(
                "--environment-baseline-id",
                default="20260611_rk3588_8gb_env_baseline",
            )
        if command == "start":
            subparser.add_argument("--startup-wait-sec", type=float, default=3.0)
    args = parser.parse_args()
    if args.command == "start":
        return start(args)
    if args.command == "run":
        return run(args)
    if args.command == "status":
        return status(args)
    return stop(args)


if __name__ == "__main__":
    raise SystemExit(main())
