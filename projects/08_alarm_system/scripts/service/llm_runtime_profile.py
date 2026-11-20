#!/usr/bin/env python3
"""Process-local, hash-pinned LLM profiles; never change the VLM environment."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within_root(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"LLM runtime profile path escapes repository: {relative}")
    return path


def load_runtime_profile(reference: str, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    source = _within_root(root, reference)
    profile = json.loads(source.read_text(encoding="utf-8"))
    profile_id = profile.get("profile_id")
    if profile_id not in {"p08_llm_stage4_h12", "p08_llm_stage6_scheme2", "p08_llm_stage6_scheme3"}:
        raise ValueError("Unsupported production LLM runtime profile")
    expected = {
        "P08_LLM_KV_PAD": "64",
        "P08_LLM_Q8_ROW_GROUP": "1",
        "P08_LLM_Q8_SHAPE_MAP": "1024x151936:2",
    }
    if profile_id in {"p08_llm_stage6_scheme2", "p08_llm_stage6_scheme3"}:
        expected.update({"P08_LLM_SHARED_PREP": "off", "P08_LLM_SHARED_PLAN": "lean",
                         "P08_LLM_FFN_FUSION": "b2", "P08_LLM_NORM_ROPE": "scheduled"})
    if profile_id == "p08_llm_stage6_scheme3":
        expected["P08_LLM_RESIDUAL_NORM"] = "sum"
    if profile.get("environment") != expected:
        raise ValueError("LLM profile requires exact inherited policies and selected fusion environment")
    fixed = {"context": 512, "max_output_tokens": 128, "threads": 6,
             "threads_batch": 6, "prompt_cache_ram_mib": 300,
             "ngl": 0, "device": "none", "no_kv_offload": True,
             "temperature": 0.0, "parallel": 1, "jinja": True}
    for key, value in fixed.items():
        if profile.get(key) != value:
            raise ValueError(f"LLM profile requires {key}={value!r}")
    if profile.get("cpu_affinity") != list(range(6)):
        raise ValueError("LLM profile requires CPU0-5")
    if [item["name"] for item in profile["libraries"]] != ["libllama", "libggml-cpu"]:
        raise ValueError("LLM profile requires exactly the pinned llama and CPU libraries")
    if profile_id in {"p08_llm_stage6_scheme2", "p08_llm_stage6_scheme3"}:
        pins = {"libllama": "ca008c5b682f2f7fbdcd3d8f0315eebfcd437f36ed01b793970f42024163ab9f",
                "libggml-cpu": ("24338e06ae161976edf0fffaa72437b50c533c985d6bc7f327d51d26d1edf619"
                                if profile_id == "p08_llm_stage6_scheme3" else
                                "ce7a1cad828b81e8c4016822c6626ef1750d80ad9dc36339dba5baaf84f84652")}
        if any(item.get("sha256") != pins[item["name"]] for item in profile["libraries"]):
            raise ValueError(f"{profile_id} requires the validated formal fusion library hashes")
    for item in profile["libraries"]:
        item["resolved_path"] = str(_within_root(root, item["path"]))
    profile["source_path"] = str(source)
    profile["source_sha256"] = sha256(source)
    return profile


def verify_runtime_artifacts(profile: dict[str, Any], server: Path, model: Path) -> dict[str, str]:
    files = [("server", server, profile["server_sha256"]),
             ("model", model, profile["model_sha256"])]
    files.extend((item["name"], Path(item["resolved_path"]), item["sha256"])
                 for item in profile["libraries"])
    actual = {}
    for name, path, expected in files:
        actual[name] = sha256(path)
        if actual[name] != expected:
            raise ValueError(f"LLM artifact hash mismatch: {name}: {path}")
    return actual


def profile_environment(profile: dict[str, Any], server: Path) -> dict[str, str]:
    child = dict(os.environ)
    prefixes = ("P08_D0_", "P08_STAGE3_", "P08_S4_", "P08_LLM_", "P08_RELIABLE_",
                "P08_NR_", "P08_RES_", "P08_S6_", "P08_S5_", "P08_FFN_")
    for key in list(child):
        if key.startswith(prefixes) or key in {"PROMPT_RESTORE_VARIANT", "GGML_BACKEND_PATH"}:
            child.pop(key)
    directories = [str(Path(item["resolved_path"]).parent) for item in profile["libraries"]]
    child["LD_LIBRARY_PATH"] = os.pathsep.join(directories + [str(server.resolve().parent)])
    child.update(profile["environment"])
    return child


def verify_loaded_libraries(profile: dict[str, Any], pid: int) -> dict[str, str]:
    paths = set()
    for line in Path(f"/proc/{pid}/maps").read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and Path(fields[5]).is_absolute():
            paths.add(fields[5])
    loaded = {}
    for item in profile["libraries"]:
        expected = Path(item["resolved_path"]).resolve()
        matches = [path for path in paths if Path(path).name.startswith(item["name"] + ".so")]
        if not matches or any(Path(path).resolve() != expected for path in matches):
            raise RuntimeError(f"LLM loaded unexpected {item['name']}: {matches}")
        loaded[item["name"]] = str(expected)
    return loaded
