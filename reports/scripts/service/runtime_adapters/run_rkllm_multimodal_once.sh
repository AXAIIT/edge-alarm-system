#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: run_rkllm_multimodal_once.sh \
  --runner PATH --vision MODEL.rknn --decoder MODEL.rkllm --image IMAGE \
  --prompt TEXT --metrics-json PATH [--output-path PATH] \
  [--max-output-tokens N] [--max-context-len N] [--npu-core-num N] [--timeout-sec N] \
  [--img-start TEXT] [--img-end TEXT] [--img-content TEXT] [--template-style STYLE]
EOF
}

RUNNER=""
VISION=""
DECODER=""
IMAGE=""
PROMPT=""
METRICS_JSON=""
OUTPUT_PATH=""
MAX_OUTPUT_TOKENS=256
MAX_CONTEXT_LEN=2048
NPU_CORE_NUM=3
TIMEOUT_SEC=600
TARGET_PLATFORM="rk3588"
IMG_START="<|vision_start|>"
IMG_END="<|vision_end|>"
IMG_CONTENT="<|image_pad|>"
TEMPLATE_STYLE="qwen"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --runner) RUNNER="$2"; shift 2 ;;
    --vision) VISION="$2"; shift 2 ;;
    --decoder) DECODER="$2"; shift 2 ;;
    --image|--input) IMAGE="$2"; shift 2 ;;
    --prompt) PROMPT="$2"; shift 2 ;;
    --metrics-json) METRICS_JSON="$2"; shift 2 ;;
    --output-path) OUTPUT_PATH="$2"; shift 2 ;;
    --max-output-tokens) MAX_OUTPUT_TOKENS="$2"; shift 2 ;;
    --max-context-len) MAX_CONTEXT_LEN="$2"; shift 2 ;;
    --npu-core-num) NPU_CORE_NUM="$2"; shift 2 ;;
    --timeout-sec) TIMEOUT_SEC="$2"; shift 2 ;;
    --target-platform) TARGET_PLATFORM="$2"; shift 2 ;;
    --img-start) IMG_START="$2"; shift 2 ;;
    --img-end) IMG_END="$2"; shift 2 ;;
    --img-content) IMG_CONTENT="$2"; shift 2 ;;
    --template-style) TEMPLATE_STYLE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "${RUNNER}" ] || [ -z "${VISION}" ] || [ -z "${DECODER}" ] || [ -z "${IMAGE}" ] || [ -z "${PROMPT}" ] || [ -z "${METRICS_JSON}" ]; then
  usage
  exit 2
fi

RUNNER="$(readlink -f "${RUNNER}")"
VISION="$(readlink -f "${VISION}")"
DECODER="$(readlink -f "${DECODER}")"
IMAGE="$(readlink -f "${IMAGE}")"
RUNNER_DIR="$(cd "$(dirname "${RUNNER}")" && pwd)"

mkdir -p "$(dirname "${METRICS_JSON}")"
[ -z "${OUTPUT_PATH}" ] || mkdir -p "$(dirname "${OUTPUT_PATH}")"

TMP_LOG="$(mktemp)"
START_MS="$(date +%s%3N)"
EXIT_CODE=0

(
  cd "${RUNNER_DIR}"
  export LD_LIBRARY_PATH="${RUNNER_DIR}/lib:/usr/lib:/lib:${LD_LIBRARY_PATH:-}"
  timeout "${TIMEOUT_SEC}" "${RUNNER}" \
    "${IMAGE}" \
    "${VISION}" \
    "${DECODER}" \
    "${PROMPT}" \
    "${MAX_OUTPUT_TOKENS}" \
    "${MAX_CONTEXT_LEN}" \
    "${NPU_CORE_NUM}" \
    "${TARGET_PLATFORM}" \
    "${IMG_START}" \
    "${IMG_END}" \
    "${IMG_CONTENT}" \
    "${TEMPLATE_STYLE}"
) >"${TMP_LOG}" 2>&1 || EXIT_CODE=$?

END_MS="$(date +%s%3N)"
TOTAL_MS=$((END_MS - START_MS))

cat "${TMP_LOG}"
[ -z "${OUTPUT_PATH}" ] || cp "${TMP_LOG}" "${OUTPUT_PATH}"

python3 - "$TMP_LOG" "$METRICS_JSON" "$EXIT_CODE" "$TOTAL_MS" "$PROMPT" <<'PY'
import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
metrics_path = Path(sys.argv[2])
exit_code = int(sys.argv[3])
total_ms = int(sys.argv[4])
prompt = sys.argv[5]
text = log_path.read_text(encoding="utf-8", errors="replace")

def first_float(pattern):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None

llm_load_ms = first_float(r"LLM Model loaded in\s+([0-9.]+)\s+ms")
imgenc_load_ms = first_float(r"ImgEnc Model loaded in\s+([0-9.]+)\s+ms")
imgenc_infer_ms = first_float(r"ImgEnc Model inference took\s+([0-9.]+)\s+ms")

robot_parts = re.findall(r"robot:\s*(.*?)(?=\n(?:user:|I rkllm:|$))", text, flags=re.S)
output_text = robot_parts[-1].strip() if robot_parts else ""

def token_approx(s: str) -> int:
    ascii_words = 0
    in_word = False
    non_ascii = 0
    punct = 0
    for ch in s:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            if not in_word:
                ascii_words += 1
                in_word = True
        else:
            in_word = False
            if ord(ch) > 127:
                non_ascii += 1
            elif not ch.isspace():
                punct += 1
    return max(0, ascii_words + non_ascii + punct)

output_tokens = token_approx(output_text)
prompt_tokens = token_approx(prompt)
load_ms = sum(x for x in [llm_load_ms, imgenc_load_ms] if x is not None)
decode_base_ms = max(0.0, total_ms - load_ms - (imgenc_infer_ms or 0.0))
decode_tps = (output_tokens * 1000.0 / decode_base_ms) if output_tokens and decode_base_ms > 0 else None

metrics = {
    "status": "pass" if exit_code == 0 and output_text else "failed",
    "exit_code": exit_code,
    "timed_out": exit_code == 124,
    "load_time_s": round(load_ms / 1000.0, 6) if load_ms else None,
    "llm_load_time_ms": llm_load_ms,
    "imgenc_load_time_ms": imgenc_load_ms,
    "image_preprocess_time_ms": imgenc_infer_ms,
    "first_token_latency_ms": None,
    "prefill_time_ms": None,
    "generate_time_ms": round(decode_base_ms, 3),
    "total_time_ms": total_ms,
    "decode_tokens_per_s": round(decode_tps, 6) if decode_tps is not None else None,
    "prompt_tokens": prompt_tokens,
    "output_tokens": output_tokens,
    "output_text": output_text,
}
metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

rm -f "${TMP_LOG}"
exit "${EXIT_CODE}"
