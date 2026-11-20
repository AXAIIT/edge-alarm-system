"""Load the explicitly selected VLM prompt/sampler without changing placement."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from llm_runtime_profile import sha256, verify_loaded_libraries

PROMPT_POLICY_ID = "original_business_prompt_q_v1"
ORIGINAL_PROFILE = "p08_vlm_original_q_runtime_v1"
Q6_PROFILE = "p08_vlm_stage4_q6_vocab_runtime_v1"
QKV_PROFILE = "p08_vlm_stage5_qkv_shared_runtime_v1"
SHARED_PREP_PROFILE = "p08_vlm_stage5_shared_prep_runtime_v1"
FFN_PROFILE = "p08_vlm_stage6_ffn_runtime_v1"
MROPE_PROFILE = "p08_vlm_stage6_mrope_runtime_v1"
RESIDUAL_PROFILE = "p08_vlm_stage6_residual_runtime_v1"
Q4_FFN_PROFILE = "p08_vlm_stage7_q4_ffn_runtime_v1"
GQA_PROFILE = "p08_vlm_stage8_gqa_runtime_v1"
VISION_MMA_PROFILE = "p08_vlm_stage9_vision_sm72_mma_runtime_v1"
VISION_CAST_PROFILE = "p08_vlm_stage10_vision_cast_runtime_v1"
VISION_AFFINE_PROFILE = "p08_vlm_stage13_vision_affine_coupled_runtime_v1"
LANGUAGE_CAST_PROFILE = "p08_vlm_stage16_language_cast_runtime_v1"
FFN_DOWN_PROFILE = "p08_vlm_stage17_ffn_down_runtime_v1"
PROJECTIONS_PROFILE = "p08_vlm_stage19_projections_runtime_v1"
REPAIRED_KV64_PROFILE = "p08_vlm_stage19_kv64_runtime_v1"
VISION_GEMM_PROFILE = "p08_vlm_stage22_c03_vision_gemm_runtime_v1"
LANGUAGE_GEMM_PROFILE = "p08_vlm_stage26_c03_language_gemm_runtime_v1"
PREFETCH_PROFILE = "p08_vlm_stage27_c06_prefetch_runtime_v1"
LANGUAGE_GEMM_PROFILES = {LANGUAGE_GEMM_PROFILE, PREFETCH_PROFILE}
VISION_GEMM_PROFILES = {VISION_GEMM_PROFILE, *LANGUAGE_GEMM_PROFILES}
PROJECTION_MATRIX = "down+q+k+v_q4+v_q6+attn_out"
DECODE_MATRIX_POLICIES = {FFN_DOWN_PROFILE: "down", PROJECTIONS_PROFILE: PROJECTION_MATRIX, REPAIRED_KV64_PROFILE: PROJECTION_MATRIX, **dict.fromkeys(VISION_GEMM_PROFILES, PROJECTION_MATRIX)}
LANGUAGE_CAST_PROFILES = {LANGUAGE_CAST_PROFILE, *DECODE_MATRIX_POLICIES}
VISION_AFFINE_PROFILES = {VISION_AFFINE_PROFILE, *LANGUAGE_CAST_PROFILES}
VISION_CAST_PROFILES = {VISION_CAST_PROFILE, *VISION_AFFINE_PROFILES}
VISION_MMA_PROFILES = {VISION_MMA_PROFILE, *VISION_CAST_PROFILES}
GQA_PROFILES = {GQA_PROFILE, *VISION_MMA_PROFILES}
VISION_CAST_FLAGS = (
    "P08_VLM_VISION_KV_CAST4",
    "P08_VLM_VISION_DENSE_CAST_IN",
    "P08_VLM_VISION_DENSE_CAST_OUT",
    "P08_VLM_VISION_CAST_BIAS",
)
Q4_FFN_PROFILES = {Q4_FFN_PROFILE, *GQA_PROFILES}
RESIDUAL_PROFILES = {RESIDUAL_PROFILE, *Q4_FFN_PROFILES}
MROPE_PROFILES = {MROPE_PROFILE, *RESIDUAL_PROFILES}
FFN_PROFILES = {FFN_PROFILE, *MROPE_PROFILES}
SHARED_PREP_POLICIES = {QKV_PROFILE: "QKV", SHARED_PREP_PROFILE: "BOTH", **dict.fromkeys(FFN_PROFILES, "BOTH")}
SAMPLING_KEYS = frozenset((
    "temperature", "top_k", "top_p", "min_p", "top_n_sigma", "xtc_probability",
    "xtc_threshold", "typical_p", "repeat_last_n", "repeat_penalty",
    "presence_penalty", "frequency_penalty", "dry_multiplier", "dry_base",
    "dry_allowed_length", "dry_penalty_last_n", "mirostat", "mirostat_tau",
    "mirostat_eta", "dynatemp_range", "dynatemp_exponent", "ignore_eos", "samplers",
))


def validate_preload(item: Any, name: str, repo: Path) -> None:
    if (not isinstance(item, dict) or item.get("name") != name
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
        raise ValueError(f"VLM profile requires a pinned {name} library")
    path = (repo / item["path"]).resolve()
    if repo.resolve() not in path.parents or path.name != name + ".so":
        raise ValueError(f"invalid VLM preload path for {name}")
    # ld.so splits LD_PRELOAD on whitespace and colons.
    posix_path = path.as_posix()
    if re.search(r"[\s:]", posix_path if os.name != "nt" else posix_path[2:]):
        raise ValueError(f"VLM path for {name} is incompatible with LD_PRELOAD")
    item["resolved_path"] = str(path)


def validate_language_artifact(item: Any, name: str, filename: str, repo: Path) -> None:
    if (not isinstance(item, dict) or item.get("name") != name
            or not isinstance(item.get("path"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256")))):
        raise ValueError(f"VLM profile requires a pinned {name} artifact")
    path = (repo / item["path"]).resolve()
    if repo.resolve() not in path.parents or path.name != filename:
        raise ValueError(f"invalid VLM artifact path for {name}")
    item["resolved_path"] = str(path)


def load_runtime_profile(reference: str | None, repo: Path) -> dict[str, Any] | None:
    if not reference:
        return None
    path = Path(reference)
    if not path.is_absolute():
        path = repo / path
    profile = json.loads(path.read_text(encoding="utf-8"))
    if (profile.get("schema_version") != "1.0"
            or profile.get("profile_id") not in {ORIGINAL_PROFILE, Q6_PROFILE, *SHARED_PREP_POLICIES}
            or profile.get("prompt_policy") != PROMPT_POLICY_ID
            or set(profile.get("sampling", {})) != SAMPLING_KEYS
            or type(profile.get("seed")) is not int or profile["seed"] < 0
            or profile.get("cache_prompt") is not True
            or type(profile.get("cache_ram_mib")) is not int
            or not 0 <= profile["cache_ram_mib"] <= 300):
        raise ValueError("invalid VLM production prompt/sampling profile")
    kernel = profile.get("cpu_kernel")
    if profile["profile_id"] in {Q6_PROFILE, *SHARED_PREP_POLICIES}:
        if not isinstance(kernel, dict) or kernel.get("policy") != "q6_vocab_neon":
            raise ValueError("VLM Q6 profile requires the vocabulary kernel")
        shared_prep = SHARED_PREP_POLICIES.get(profile["profile_id"])
        if shared_prep is not None and kernel.get("shared_prep") != shared_prep:
            raise ValueError(f"VLM shared preparation profile requires {shared_prep}")
        if shared_prep is None and "shared_prep" in kernel:
            raise ValueError("VLM stage 4 profile cannot select shared preparation")
        if profile["profile_id"] in FFN_PROFILES:
            if kernel.get("ffn_fusion") is not True:
                raise ValueError("VLM FFN profile requires FFN fusion")
        elif "ffn_fusion" in kernel:
            raise ValueError("VLM profile does not select FFN fusion")
        if profile["profile_id"] in MROPE_PROFILES:
            if kernel.get("mrope_fusion") is not True:
                raise ValueError("VLM MRoPE profile requires MRoPE fusion")
        elif "mrope_fusion" in kernel:
            raise ValueError("VLM profile does not select MRoPE fusion")
        if profile["profile_id"] in RESIDUAL_PROFILES:
            if kernel.get("residual_norm_fusion") is not True:
                raise ValueError("VLM residual profile requires residual norm fusion")
        elif "residual_norm_fusion" in kernel:
            raise ValueError("VLM profile does not select residual norm fusion")
        if profile["profile_id"] in Q4_FFN_PROFILES:
            if kernel.get("q4_ffn_dot") is not True:
                raise ValueError("VLM stage 7 profile requires Q4 FFN dot")
        elif "q4_ffn_dot" in kernel:
            raise ValueError("VLM profile does not select the Q4 FFN dot")
        if profile["profile_id"] in GQA_PROFILES:
            if kernel.get("gqa_pair") is not True:
                raise ValueError("VLM stage 8 profile requires paired GQA")
        elif "gqa_pair" in kernel:
            raise ValueError("VLM profile does not select paired GQA")
        library = kernel["library"]
        dependencies = kernel["dependencies"]
        if (library["name"] != "libggml-cpu"
                or [item["name"] for item in dependencies] != ["libllama", "libggml-cuda", "libmtmd"]
                or any(Path(item["path"]).name != item["path"]
                       or not item["path"].startswith(item["name"] + ".so") for item in dependencies)
                or set(kernel["models_sha256"]) != {"language", "mmproj"}):
            raise ValueError("invalid VLM Q6 runtime identity")
        digests = [kernel["server_sha256"], *kernel["models_sha256"].values(),
                   *(item["sha256"] for item in [library, *dependencies])]
        if any(not re.fullmatch("[0-9a-f]{64}", value) for value in digests):
            raise ValueError("invalid VLM artifact SHA256")
        path = (repo / library["path"]).resolve()
        try:
            path.relative_to(repo.resolve())
        except ValueError:
            raise ValueError("VLM CPU library must be inside the repository") from None
        if path.name != "libggml-cpu.so.0":
            raise ValueError("invalid VLM CPU library path")
        library["resolved_path"] = str(path)
        override = kernel.get("vision_cuda")
        if profile["profile_id"] in VISION_MMA_PROFILES:
            if (not isinstance(override, dict)
                    or not isinstance(override.get("path"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", override.get("sha256", ""))):
                raise ValueError("VLM stage 9 requires a pinned CUDA library")
            cuda = (repo / override["path"]).resolve()
            if (repo.resolve() not in cuda.parents
                    or cuda.name != dependencies[1]["path"] or cuda.parent == path.parent):
                raise ValueError("invalid VLM stage 9 CUDA library path")
            override["resolved_path"] = str(cuda)
        elif "vision_cuda" in kernel:
            raise ValueError("VLM profile does not select SM72 vision MMA")
        if profile["profile_id"] in VISION_CAST_PROFILES:
            validate_preload(kernel.get("vision_cast"), "stage10_bias_v3", repo)
        elif "vision_cast" in kernel:
            raise ValueError("VLM profile does not select stage 10 vision casts")
        if profile["profile_id"] in VISION_AFFINE_PROFILES:
            preloads = kernel.get("vision_affine")
            if not isinstance(preloads, list) or len(preloads) != 2:
                raise ValueError("VLM stage 13 requires the tested vision preload chain")
            for item, name in zip(preloads, ("affine", "c13_fusion")):
                validate_preload(item, name, repo)
        elif "vision_affine" in kernel:
            raise ValueError("VLM profile does not select stage 13 vision normalization")
        if profile["profile_id"] in LANGUAGE_CAST_PROFILES:
            validate_preload(kernel.get("language_cast"), "language_fusion_v2", repo)
        elif "language_cast" in kernel:
            raise ValueError("VLM profile does not select stage 16 language casts")
        if profile["profile_id"] in {REPAIRED_KV64_PROFILE, *VISION_GEMM_PROFILES}:
            if type(kernel.get("kv_alignment")) is not int or kernel["kv_alignment"] != 64:
                raise ValueError("VLM KV64 requires repaired 64-position alignment")
        elif "kv_alignment" in kernel:
            raise ValueError("VLM profile does not select repaired KV64")
        if profile["profile_id"] in VISION_GEMM_PROFILES:
            gemm = kernel.get("vision_gemm")
            validate_preload(gemm, "vision_gemm_policy", repo)
            if type(gemm.get("mask")) is not int or gemm["mask"] != 7:
                raise ValueError("VLM C03 requires the validated three visual GEMM groups")
        elif "vision_gemm" in kernel:
            raise ValueError("VLM profile does not select C03 vision GEMM")
        if profile["profile_id"] in LANGUAGE_GEMM_PROFILES:
            language_gemm = kernel.get("language_gemm")
            if not isinstance(language_gemm, dict):
                raise ValueError("VLM language GEMM requires its tested policy and preload")
            name = "prefetch_scope" if profile["profile_id"] == PREFETCH_PROFILE else "language_gemm"
            validate_preload(language_gemm.get("preload"), name, repo)
            validate_language_artifact(language_gemm.get("policy"), "image_eval_gemm_policy", "image_only_policy.txt", repo)
        elif "language_gemm" in kernel:
            raise ValueError("VLM profile does not select language GEMM")
        if profile["profile_id"] == PREFETCH_PROFILE:
            prefetch = kernel.get("prefetch")
            if not isinstance(prefetch, dict) or type(prefetch.get("mask")) is not int or prefetch["mask"] != 3:
                raise ValueError("VLM prefetch requires the validated joint policy")
            validate_language_artifact(prefetch.get("base"), "libggml-base", "libggml-base.so.0.15.2", repo)
        elif "prefetch" in kernel:
            raise ValueError("VLM profile does not select weight prefetch")
        expected_matrix = DECODE_MATRIX_POLICIES.get(profile["profile_id"])
        if kernel.get("decode_matrix") != expected_matrix or ("decode_matrix" in kernel and expected_matrix is None):
            raise ValueError("invalid VLM Decode matrix policy")
    elif kernel is not None:
        raise ValueError("legacy VLM profile cannot select a CPU kernel")
    return profile


def kernel_startup(kernel: dict[str, Any], server: Path, model: Path, mmproj: Path):
    server = server.resolve()
    library = kernel["library"]
    libraries = [library, *[
        dict(item, resolved_path=str((server.parent / item["path"]).resolve()))
        for item in kernel["dependencies"]
    ]]
    if kernel.get("kv_alignment") == 64:
        local_llama = Path(library["resolved_path"]).parent / kernel["dependencies"][0]["path"]
        soname = local_llama.with_name("libllama.so.0")
        if not soname.is_file() or not local_llama.is_file() or not soname.samefile(local_llama):
            raise ValueError("VLM KV64 libllama SONAME link mismatch")
        libraries[1]["resolved_path"] = str(local_llama)
    vision_cuda = kernel.get("vision_cuda")
    vision_cast = kernel.get("vision_cast")
    vision_affine = kernel.get("vision_affine", [])
    language_cast = kernel.get("language_cast")
    vision_gemm = kernel.get("vision_gemm")
    language_gemm = kernel.get("language_gemm")
    prefetch = kernel.get("prefetch")
    directories = [str(Path(library["resolved_path"]).parent)]
    if vision_cuda:
        cuda = Path(vision_cuda["resolved_path"])
        libraries[2] = dict(name="libggml-cuda", resolved_path=str(cuda), sha256=vision_cuda["sha256"])
        directories.insert(0, str(cuda.parent))
    if vision_cast:
        preloads = [language_cast, *vision_affine, vision_cast] if language_cast else [*vision_affine, vision_cast]
        if vision_gemm:
            preloads.insert(0, vision_gemm)
        if language_gemm:
            preloads.insert(0, language_gemm["preload"])
        libraries.extend(preloads)
    if prefetch:
        base = Path(prefetch["base"]["resolved_path"])
        soname = base.with_name("libggml-base.so.0")
        if not base.is_file() or not soname.is_file() or not soname.samefile(base):
            raise ValueError("VLM prefetch libggml-base SONAME link mismatch")
        directories.insert(0, str(base.parent))
        libraries.append(prefetch["base"])
    artifacts = [("server", server, kernel["server_sha256"]),
                 ("language", model, kernel["models_sha256"]["language"]),
                 ("mmproj", mmproj, kernel["models_sha256"]["mmproj"])]
    artifacts.extend((item["name"], Path(item["resolved_path"]), item["sha256"]) for item in libraries)
    if language_gemm:
        policy = language_gemm["policy"]
        artifacts.append((policy["name"], Path(policy["resolved_path"]), policy["sha256"]))
    for name, path, expected in artifacts:
        if sha256(path) != expected:
            raise ValueError(f"VLM artifact hash mismatch: {name}: {path}")
    child = {key: value for key, value in os.environ.items()
             if not key.startswith(("P08_", "GGML_", "LLAMA_", "PROJECT08_"))
             and key not in {"LD_PRELOAD", "LD_AUDIT"}}
    child["LD_LIBRARY_PATH"] = os.pathsep.join([*directories, str(server.parent)])
    if vision_cuda:
        child["P08_VLM_VISION_SM72_MMA"] = "1"
    if vision_cast:
        child["LD_PRELOAD"] = ":".join(item["resolved_path"] for item in preloads)
        child.update(dict.fromkeys(VISION_CAST_FLAGS, "1"))
    if vision_affine:
        child["P08_STAGE13"] = "coupled"
        child["P08_C13"] = "off"
    if language_cast:
        child["P08_C04_LANGUAGE_CAST"] = "combo"
    if "decode_matrix" in kernel:
        child["P08_DECODE_MATRIX"] = kernel["decode_matrix"]
    if kernel.get("kv_alignment") == 64:
        child["P08_VLM_KV_MIN_PAD"] = "64"
        child["P08_VLM_KV_REPAIR"] = "1"
    if vision_gemm:
        child["P08_C03_VISION_GEMM_MASK"] = str(vision_gemm["mask"])
    if language_gemm:
        child["P08_LANGUAGE_GEMM_POLICY"] = language_gemm["policy"]["resolved_path"]
    if prefetch:
        child["P08_PREFETCH_MASK"] = str(prefetch["mask"])
        child["GGML_CUDA_DISABLE_GRAPHS"] = "1"
    child["P08_VLM_Q6_VOCAB"] = "1"
    if kernel.get("shared_prep") in {"QKV", "BOTH"}:
        child["P08_VLM_SHARED_PREP"] = kernel["shared_prep"]
    if kernel.get("ffn_fusion") is True:
        child["P08_VLM_FFN_FUSION"] = "1"
    if kernel.get("mrope_fusion") is True:
        child["P08_VLM_MROPE_FUSION"] = "1"
    if kernel.get("residual_norm_fusion") is True:
        child["P08_VLM_RESIDUAL_NORM"] = "1"
    if kernel.get("q4_ffn_dot") is True:
        child["P08_VLM_Q4_FFN_DOT"] = "1"
    if kernel.get("gqa_pair") is True:
        child["P08_VLM_GQA_PAIR"] = "1"
    return child, libraries


def verify_kernel_loaded(libraries: list[dict[str, str]], pid: int) -> dict[str, str]:
    return verify_loaded_libraries({"libraries": libraries}, pid)
