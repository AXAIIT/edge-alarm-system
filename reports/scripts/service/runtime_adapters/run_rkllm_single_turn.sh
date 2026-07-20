#!/usr/bin/env bash
set -euo pipefail

RUNNER=""
MODEL=""
PROMPT=""
MAX_TOKENS=160
MAX_CTX=2048
METRICS_JSON=""
RUN_TIMEOUT_SEC="${RUN_TIMEOUT_SEC:-300}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runner) RUNNER="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --prompt) PROMPT="$2"; shift 2 ;;
    --max-output-tokens) MAX_TOKENS="$2"; shift 2 ;;
    --max-context-len) MAX_CTX="$2"; shift 2 ;;
    --metrics-json) METRICS_JSON="$2"; shift 2 ;;
    --timeout-sec) RUN_TIMEOUT_SEC="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "${RUNNER}" ]]; then
  for candidate in \
    ./rkllm_single_turn \
    projects/05_alarm_system/runners/rkllm_single_turn/build/rkllm_single_turn \
    projects/05_alarm_system/runners/rkllm_single_turn/install/rkllm_single_turn; do
    if [[ -x "${candidate}" ]]; then
      RUNNER="${candidate}"
      break
    fi
  done
fi

if [[ -z "${RUNNER}" || ! -x "${RUNNER}" ]]; then
  [[ -n "${METRICS_JSON}" ]] && mkdir -p "$(dirname "${METRICS_JSON}")"
  [[ -n "${METRICS_JSON}" ]] && echo '{"status":"error","error":"rkllm_single_turn runner not found"}' > "${METRICS_JSON}"
  echo "ERROR: rkllm_single_turn runner not found; pass --runner or build projects/05_alarm_system/runners/rkllm_single_turn." >&2
  exit 1
fi

if [[ -z "${MODEL}" || -z "${PROMPT}" ]]; then
  echo "ERROR: --model and --prompt are required." >&2
  exit 2
fi

if [[ -n "${METRICS_JSON}" ]]; then
  mkdir -p "$(dirname "${METRICS_JSON}")"
fi

timeout --kill-after=5s "${RUN_TIMEOUT_SEC}s" taskset f0 "${RUNNER}" \
  --model "${MODEL}" \
  --prompt "${PROMPT}" \
  --max-output-tokens "${MAX_TOKENS}" \
  --max-context-len "${MAX_CTX}" \
  --metrics-json "${METRICS_JSON}"
