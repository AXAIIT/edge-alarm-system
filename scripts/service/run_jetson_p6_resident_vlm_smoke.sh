#!/usr/bin/env bash
set -euo pipefail

BOARD="${BOARD:-jetson_8gb}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d)_jetson_8gb_alarm_service_resident_vlm_smoke_v1}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
EVENTS_INPUT="${EVENTS_INPUT:-benchmark/raw/05_alarm_system/${BOARD}/events/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_events.jsonl}"
MODEL_CONFIG="${MODEL_CONFIG:-projects/05_alarm_system/configs/models/jetson_model_combo.yaml}"
VLM_MODEL="${VLM_MODEL:-${QWEN3_VL_GGUF:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf}}"
MMPROJ_MODEL="${MMPROJ_MODEL:-${QWEN3_VL_MMPROJ:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf}}"
LLAMA_BIN_VALUE="${LLAMA_BIN:-llama-cli}"
LLAMA_SERVER_BIN_VALUE="${LLAMA_SERVER_BIN:-}"
MAX_EVENTS="${MAX_EVENTS:-3}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-0}"
VLM_MAX_CALLS="${VLM_MAX_CALLS:-3}"
VLM_CTX="${VLM_CTX:-1536}"
VLM_MAX_TOKENS="${VLM_MAX_TOKENS:-96}"
VLM_TIMEOUT_MS="${VLM_TIMEOUT_MS:-180000}"
VLM_STARTUP_TIMEOUT_MS="${VLM_STARTUP_TIMEOUT_MS:-180000}"
VLM_NGL="${VLM_NGL:-0}"
VLM_DEVICE="${VLM_DEVICE:-}"
VLM_IMAGE_MIN_TOKENS="${VLM_IMAGE_MIN_TOKENS:-512}"
VLM_IMAGE_MAX_TOKENS="${VLM_IMAGE_MAX_TOKENS:-512}"
VLM_NO_MMPROJ_OFFLOAD="${VLM_NO_MMPROJ_OFFLOAD:-1}"
VLM_NO_KV_OFFLOAD="${VLM_NO_KV_OFFLOAD:-1}"
VLM_REQUEST_RETRIES="${VLM_REQUEST_RETRIES:-1}"
ASSET_SOURCE_URI="${ASSET_SOURCE_URI:-data/videos/runtime_playlist_v1.txt}"

export BOARD RUN_ID

if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi
if [[ -z "${VLM_MODEL}" || -z "${MMPROJ_MODEL}" ]]; then
  echo "VLM_MODEL/QWEN3_VL_GGUF and MMPROJ_MODEL/QWEN3_VL_MMPROJ are required"
  exit 2
fi
if [[ -z "${LLAMA_BIN_VALUE}" && -z "${LLAMA_SERVER_BIN_VALUE}" ]]; then
  echo "LLAMA_BIN or LLAMA_SERVER_BIN is required"
  exit 2
fi

mkdir -p \
  "benchmark/raw/05_alarm_system/${BOARD}/events" \
  "benchmark/raw/05_alarm_system/${BOARD}/alarms" \
  "benchmark/processed/05_alarm_system" \
  "logs/runtime/05_alarm_system/${BOARD}" \
  "logs/benchmark/05_alarm_system/${BOARD}"

echo "resident_vlm_smoke_mode=llama_cpp_multimodal_resident"
echo "vlm_ngl=${VLM_NGL}"
echo "vlm_device=${VLM_DEVICE:-auto}"
echo "vlm_no_kv_offload=${VLM_NO_KV_OFFLOAD}"
echo "vlm_no_mmproj_offload=${VLM_NO_MMPROJ_OFFLOAD}"
echo "vlm_timeout_ms=${VLM_TIMEOUT_MS}"
echo "vlm_startup_timeout_ms=${VLM_STARTUP_TIMEOUT_MS}"
echo "vlm_request_retries=${VLM_REQUEST_RETRIES}"

test -s "${EVENTS_INPUT}"
test -s "${MODEL_CONFIG}"
test -s "${VLM_MODEL}"
test -s "${MMPROJ_MODEL}"
test -s "${ASSET_SOURCE_URI}"

LLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl"
VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl"
ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl"
BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl"
STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"
VLM_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_cpp_vlm_runtime"
ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_assets"

rm -f "${LLM}" "${VLM}" "${ALARMS}" "${BENCHMARK}" "${STABILITY}"
rm -rf "${VLM_RUNTIME_DIR}" "${ASSET_DIR}"
mkdir -p "${VLM_RUNTIME_DIR}" "${ASSET_DIR}"

ARGS=(
  python3 projects/05_alarm_system/scripts/service/run_alarm_service.py
  --run-id "${RUN_ID}"
  --board "${BOARD}"
  --environment-baseline-id "${ENV_BASELINE_ID}"
  --detector-mode events_input
  --events-input "${EVENTS_INPUT}"
  --model-config "${MODEL_CONFIG}"
  --asset-mode source_media
  --asset-source-type video_playlist
  --asset-source-uri "${ASSET_SOURCE_URI}"
  --asset-playlist-loop
  --asset-dir "${ASSET_DIR}"
  --asset-trigger-policy vlm_real_calls_only
  --text-mode template
  --text-max-calls "${TEXT_MAX_CALLS}"
  --vlm-mode llama_cpp_multimodal_resident
  --vlm-model-path "${VLM_MODEL}"
  --mmproj-path "${MMPROJ_MODEL}"
  --llama-bin "${LLAMA_BIN_VALUE}"
  --vlm-ctx "${VLM_CTX}"
  --vlm-max-tokens "${VLM_MAX_TOKENS}"
  --vlm-timeout-ms "${VLM_TIMEOUT_MS}"
  --vlm-startup-timeout-ms "${VLM_STARTUP_TIMEOUT_MS}"
  --vlm-runtime-log-dir "${VLM_RUNTIME_DIR}"
  --vlm-max-calls "${VLM_MAX_CALLS}"
  --vlm-request-retries "${VLM_REQUEST_RETRIES}"
  --vlm-ngl "${VLM_NGL}"
  --vlm-image-min-tokens "${VLM_IMAGE_MIN_TOKENS}"
  --vlm-image-max-tokens "${VLM_IMAGE_MAX_TOKENS}"
  --max-events "${MAX_EVENTS}"
  --status not_verified
  --service-status stopped
)

if [[ -n "${LLAMA_SERVER_BIN_VALUE}" ]]; then
  ARGS+=(--vlm-llama-server-bin "${LLAMA_SERVER_BIN_VALUE}")
fi
if [[ -n "${VLM_DEVICE}" ]]; then
  ARGS+=(--vlm-device "${VLM_DEVICE}")
fi
if [[ "${VLM_NO_MMPROJ_OFFLOAD}" == "1" ]]; then
  ARGS+=(--vlm-no-mmproj-offload)
fi
if [[ "${VLM_NO_KV_OFFLOAD}" == "1" ]]; then
  ARGS+=(--vlm-no-kv-offload)
fi

"${ARGS[@]}"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl" \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_event_package_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${ALARMS}" \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_alarm_json_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${BENCHMARK}" \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_raw_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${STABILITY}" \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_stability_schema_check.md"

python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

board = os.environ["BOARD"]
run_id = os.environ["RUN_ID"]
path = Path(f"benchmark/raw/05_alarm_system/{board}/{run_id}_vlm_outputs.jsonl")
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
bad = [row for row in rows if row.get("status") != "pass" or not row.get("vlm_summary")]
pass_rows = [row for row in rows if row.get("status") == "pass"]
pids = sorted({row.get("resident_server_pid") for row in pass_rows if row.get("resident_server_pid") is not None})
loads = sorted({row.get("resident_model_load_count") for row in pass_rows if row.get("resident_model_load_count") is not None})
indexes = [row.get("resident_request_index") for row in pass_rows if row.get("resident_request_index") is not None]
print(f"vlm_rows={len(rows)}")
print(f"vlm_bad_rows={len(bad)}")
print(f"resident_server_pids={pids}")
print(f"resident_model_load_counts={loads}")
print(f"resident_request_indexes={indexes}")
if bad:
    print("bad_event_ids=", [row.get("event_id") for row in bad[:5]])
    sys.exit(1)
if len(pids) != 1 or loads != [1]:
    raise SystemExit("Jetson resident VLM smoke failed: resident pid/load_count mismatch")
if indexes != sorted(indexes):
    raise SystemExit("Jetson resident VLM smoke failed: request indexes are not monotonic")
PY

echo "JETSON_P6_VLM_RESULT=resident_vlm_worker_smoke_pass"
