#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


CROSS_PROJECT_PATTERNS = (
    "projects/03_video_pipeline",
    "projects\\03_video_pipeline",
    "projects/04_llm_vlm_independent",
    "projects\\04_llm_vlm_independent",
)

SERVICE_PARTS = (
    ("scripts", "service"),
    ("src", "service"),
)


def is_service_path(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    for first, second in SERVICE_PARTS:
        for idx in range(0, max(0, len(parts) - 1)):
            if parts[idx] == first and parts[idx + 1] == second:
                return True
    return False


def classify(path: Path, line: str) -> str:
    normalized = line.replace("\\", "/")
    if is_service_path(path):
        return "forbidden_final_runtime"
    if "/reports/" in normalized:
        return "allowed_reference"
    if "benchmark/raw/03_video_pipeline" in normalized or "models/llm_vlm" in normalized:
        return "allowed_artifact"
    if "run_rkllm" in normalized or "rkllm_multimodal_once" in normalized:
        return "legacy_adapter_smoke"
    return "legacy_adapter_smoke"


def iter_text_files(root: Path):
    for base in (root / "scripts", root / "src"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".sh", ".md", ".txt", ".yaml", ".yml", ".json"}:
                yield path


def scan(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in iter_text_files(root):
        if path.name == "check_code_boundary.py":
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if any(pattern in line for pattern in CROSS_PROJECT_PATTERNS):
                rows.append(
                    {
                        "file": path.as_posix(),
                        "line": lineno,
                        "classification": classify(path, line),
                        "text": line.strip(),
                    }
                )
    return rows


def status_from_rows(rows: list[dict[str, object]]) -> str:
    classes = {str(row["classification"]) for row in rows}
    if "forbidden_final_runtime" in classes:
        return "coupled_runtime_not_accepted"
    if "legacy_adapter_smoke" in classes:
        return "legacy_adapter_smoke"
    if "allowed_artifact" in classes:
        return "artifact_replay_pass"
    return "independent_runtime_pass"


def render_report(root: Path, rows: list[dict[str, object]]) -> str:
    status = status_from_rows(rows)
    lines = [
        "# Project 05 code boundary check",
        "",
        f"- root: `{root.as_posix()}`",
        f"- matches: {len(rows)}",
        f"- code_boundary_status: `{status}`",
        "",
        "| classification | file | line | text |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        text = str(row["text"]).replace("|", "\\|")
        lines.append(f"| `{row['classification']}` | `{row['file']}` | {row['line']} | `{text}` |")
    if not rows:
        lines.append("| `independent_runtime_pass` |  |  | no cross-project runtime references found |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Project 05 code boundary against Project 3/4 script coupling.")
    parser.add_argument("--root", type=Path, default=Path("projects/05_alarm_system"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    rows = scan(args.root)
    report = render_report(args.root, rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
