#!/usr/bin/env bash
set -euo pipefail

BOARD="${BOARD:-jetson_8gb}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d)_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1}"
SOURCE_RUN_ID="${SOURCE_RUN_ID:-}"
EVENTS_INPUT="${EVENTS_INPUT:-}"
LLM_INPUT="${LLM_INPUT:-}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
MODEL_CONFIG="${MODEL_CONFIG:-projects/05_alarm_system/configs/models/jetson_model_combo.yaml}"
MAX_EVENTS="${MAX_EVENTS:-3}"
VLM_MAX_CALLS="${VLM_MAX_CALLS:-2}"
ASYNC_REQUIRE_PASS_ROWS="${ASYNC_REQUIRE_PASS_ROWS:-0}"
ASYNC_STOP_AFTER_BUDGET="${ASYNC_STOP_AFTER_BUDGET:-1}"
ASYNC_STARTUP_WAIT_SEC="${ASYNC_STARTUP_WAIT_SEC:-5}"
ASYNC_IDLE_TIMEOUT_SEC="${ASYNC_IDLE_TIMEOUT_SEC:-0}"
ASYNC_POLL_INTERVAL_SEC="${ASYNC_POLL_INTERVAL_SEC:-0.2}"
VLM_MODE="${VLM_MODE:-llama_cpp_multimodal_once}"
VLM_MODEL="${VLM_MODEL:-${QWEN3_VL_GGUF:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf}}"
MMPROJ_MODEL="${MMPROJ_MODEL:-${QWEN3_VL_MMPROJ:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf}}"
LLAMA_BIN_VALUE="${LLAMA_BIN:-llama-cli}"
LLAMA_SERVER_BIN_VALUE="${LLAMA_SERVER_BIN:-}"
VLM_CTX="${VLM_CTX:-1536}"
VLM_MAX_TOKENS="${VLM_MAX_TOKENS:-96}"
VLM_TIMEOUT_MS="${VLM_TIMEOUT_MS:-240000}"
VLM_STARTUP_TIMEOUT_MS="${VLM_STARTUP_TIMEOUT_MS:-240000}"
VLM_NGL="${VLM_NGL:-0}"
VLM_DEVICE="${VLM_DEVICE:-}"
VLM_IMAGE_MIN_TOKENS="${VLM_IMAGE_MIN_TOKENS:-512}"
VLM_IMAGE_MAX_TOKENS="${VLM_IMAGE_MAX_TOKENS:-512}"
VLM_NO_MMPROJ_OFFLOAD="${VLM_NO_MMPROJ_OFFLOAD:-1}"
VLM_NO_KV_OFFLOAD="${VLM_NO_KV_OFFLOAD:-1}"
VLM_REQUEST_RETRIES="${VLM_REQUEST_RETRIES:-1}"
ASSET_SOURCE_TYPE="${ASSET_SOURCE_TYPE:-video_playlist}"
ASSET_SOURCE_URI="${ASSET_SOURCE_URI:-data/videos/runtime_playlist_v1.txt}"
ASSET_PLAYLIST_LOOP="${ASSET_PLAYLIST_LOOP:-1}"

export BOARD RUN_ID

if [[ -z "${EVENTS_INPUT}" && -n "${SOURCE_RUN_ID}" ]]; then
  EVENTS_INPUT="benchmark/raw/05_alarm_system/${BOARD}/events/${SOURCE_RUN_ID}_events.jsonl"
fi
if [[ -z "${LLM_INPUT}" && -n "${SOURCE_RUN_ID}" ]]; then
  CANDIDATE_LLM_INPUT="benchmark/raw/05_alarm_system/${BOARD}/${SOURCE_RUN_ID}_llm_outputs.jsonl"
  if [[ -s "${CANDIDATE_LLM_INPUT}" ]]; then
    LLM_INPUT="${CANDIDATE_LLM_INPUT}"
  fi
fi

if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi
if [[ -z "${EVENTS_INPUT}" ]]; then
  echo "EVENTS_INPUT is required, or set SOURCE_RUN_ID to derive it"
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
  "benchmark/raw/05_alarm_system/${BOARD}/alarms" \
  "benchmark/processed/05_alarm_system" \
  "logs/runtime/05_alarm_system/${BOARD}" \
  "logs/benchmark/05_alarm_system/${BOARD}"

test -s "${EVENTS_INPUT}"
test -s "${MODEL_CONFIG}"
test -s "${VLM_MODEL}"
test -s "${MMPROJ_MODEL}"
test -e "${ASSET_SOURCE_URI}"
if [[ -n "${LLM_INPUT}" ]]; then
  test -s "${LLM_INPUT}"
fi

ASYNC_VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_outputs.jsonl"
ASYNC_ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarm_enriched.jsonl"
ASYNC_BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_enriched_benchmark.jsonl"
ASYNC_SERVICE_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_service.log"
ASYNC_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_runtime"
ASYNC_ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_assets"
ASYNC_SUMMARY="benchmark/processed/05_alarm_system/${RUN_ID}_async_vlm_summary.md"

rm -f \
  "${ASYNC_VLM}" \
  "${ASYNC_ALARMS}" \
  "${ASYNC_BENCHMARK}" \
  "${ASYNC_SERVICE_LOG}" \
  "${ASYNC_SUMMARY}"
rm -rf "${ASYNC_RUNTIME_DIR}" "${ASYNC_ASSET_DIR}"
mkdir -p "${ASYNC_RUNTIME_DIR}" "${ASYNC_ASSET_DIR}"

echo "async_vlm_mode=${VLM_MODE}"
echo "async_entrypoint=run_async_vlm_enrichment.py"
echo "source_run_id=${SOURCE_RUN_ID:-none}"
echo "events_input=${EVENTS_INPUT}"
echo "llm_input=${LLM_INPUT:-none}"
echo "asset_source_type=${ASSET_SOURCE_TYPE}"
echo "asset_source_uri=${ASSET_SOURCE_URI}"
echo "max_events=${MAX_EVENTS}"
echo "vlm_max_calls=${VLM_MAX_CALLS}"
echo "async_require_pass_rows=${ASYNC_REQUIRE_PASS_ROWS}"
echo "vlm_ngl=${VLM_NGL}"
echo "vlm_device=${VLM_DEVICE:-auto}"
echo "vlm_no_kv_offload=${VLM_NO_KV_OFFLOAD}"
echo "vlm_no_mmproj_offload=${VLM_NO_MMPROJ_OFFLOAD}"
echo "vlm_timeout_ms=${VLM_TIMEOUT_MS}"
echo "vlm_startup_timeout_ms=${VLM_STARTUP_TIMEOUT_MS}"
echo "vlm_request_retries=${VLM_REQUEST_RETRIES}"
echo "vlm_once_retry_enabled=$([[ "${VLM_MODE}" == "llama_cpp_multimodal_once" ]] && echo 1 || echo 0)"

ARGS=(
  python3 projects/05_alarm_system/scripts/service/run_async_vlm_enrichment.py
  --run-id "${RUN_ID}"
  --board "${BOARD}"
  --environment-baseline-id "${ENV_BASELINE_ID}"
  --events-input "${EVENTS_INPUT}"
  --model-config "${MODEL_CONFIG}"
  --asset-mode source_media
  --asset-source-type "${ASSET_SOURCE_TYPE}"
  --asset-source-uri "${ASSET_SOURCE_URI}"
  --asset-dir "${ASYNC_ASSET_DIR}"
  --asset-image-ext jpg
  --asset-jpeg-quality 85
  --vlm-mode "${VLM_MODE}"
  --vlm-model-path "${VLM_MODEL}"
  --mmproj-path "${MMPROJ_MODEL}"
  --llama-bin "${LLAMA_BIN_VALUE}"
  --vlm-ctx "${VLM_CTX}"
  --vlm-max-tokens "${VLM_MAX_TOKENS}"
  --vlm-timeout-ms "${VLM_TIMEOUT_MS}"
  --vlm-startup-timeout-ms "${VLM_STARTUP_TIMEOUT_MS}"
  --vlm-runtime-log-dir "${ASYNC_RUNTIME_DIR}"
  --vlm-max-calls "${VLM_MAX_CALLS}"
  --vlm-request-retries "${VLM_REQUEST_RETRIES}"
  --vlm-ngl "${VLM_NGL}"
  --vlm-image-min-tokens "${VLM_IMAGE_MIN_TOKENS}"
  --vlm-image-max-tokens "${VLM_IMAGE_MAX_TOKENS}"
  --poll-interval-sec "${ASYNC_POLL_INTERVAL_SEC}"
  --startup-wait-sec "${ASYNC_STARTUP_WAIT_SEC}"
  --idle-timeout-sec "${ASYNC_IDLE_TIMEOUT_SEC}"
  --max-events "${MAX_EVENTS}"
  --vlm-output "${ASYNC_VLM}"
  --alarm-output "${ASYNC_ALARMS}"
  --benchmark-output "${ASYNC_BENCHMARK}"
  --service-log "${ASYNC_SERVICE_LOG}"
)

if [[ -n "${LLM_INPUT}" ]]; then
  ARGS+=(--llm-input "${LLM_INPUT}")
fi
if [[ "${ASSET_SOURCE_TYPE}" == "video_playlist" && "${ASSET_PLAYLIST_LOOP}" == "1" ]]; then
  ARGS+=(--asset-playlist-loop)
fi
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
if [[ "${ASYNC_STOP_AFTER_BUDGET}" == "1" ]]; then
  ARGS+=(--stop-after-budget)
fi

"${ARGS[@]}"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${ASYNC_ALARMS}" \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_async_alarm_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${ASYNC_BENCHMARK}" \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_async_benchmark_schema_check.md"

python3 - "${EVENTS_INPUT}" "${ASYNC_VLM}" "${ASYNC_ALARMS}" "${ASYNC_BENCHMARK}" "${ASYNC_REQUIRE_PASS_ROWS}" "${ASYNC_SUMMARY}" <<'PY'
import json
import sys
from pathlib import Path

events_path = Path(sys.argv[1])
vlm_path = Path(sys.argv[2])
alarms_path = Path(sys.argv[3])
benchmark_path = Path(sys.argv[4])
required_pass_rows = int(sys.argv[5])
summary_path = Path(sys.argv[6])

event_rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
vlm_rows = [json.loads(line) for line in vlm_path.read_text(encoding="utf-8").splitlines() if line.strip()]
alarm_rows = [json.loads(line) for line in alarms_path.read_text(encoding="utf-8").splitlines() if line.strip()]
benchmark_rows = [json.loads(line) for line in benchmark_path.read_text(encoding="utf-8").splitlines() if line.strip()]

pass_rows = [row for row in vlm_rows if row.get("status") == "pass"]
fallback_rows = [row for row in vlm_rows if row.get("status") == "fallback"]
failed_rows = [row for row in vlm_rows if row.get("status") == "failed"]
blocked_rows = [row for row in vlm_rows if row.get("status") == "blocked_no_image_asset"]
not_executed_rows = [row for row in vlm_rows if row.get("status") == "not_executed"]
unknown_rows = [
    row for row in vlm_rows
    if row.get("status") not in {"pass", "fallback", "failed", "blocked_no_image_asset", "not_executed"}
]

print(f"source_event_rows={len(event_rows)}")
print(f"async_vlm_rows={len(vlm_rows)}")
print(f"async_vlm_pass_rows={len(pass_rows)}")
print(f"async_vlm_fallback_rows={len(fallback_rows)}")
print(f"async_vlm_failed_rows={len(failed_rows)}")
print(f"async_vlm_blocked_rows={len(blocked_rows)}")
print(f"async_vlm_not_executed_rows={len(not_executed_rows)}")
print(f"async_alarm_rows={len(alarm_rows)}")
print(f"async_benchmark_rows={len(benchmark_rows)}")
if unknown_rows:
    for row in unknown_rows[:5]:
        print(f"async_vlm_unknown_event={row.get('event_id')} status={row.get('status')} mode={row.get('mode')}")
    raise SystemExit("Jetson async enrichment failed: unexpected VLM row status")
if not vlm_rows:
    raise SystemExit("Jetson async enrichment failed: no async VLM rows were produced")
if len(alarm_rows) != len(vlm_rows):
    raise SystemExit("Jetson async enrichment failed: alarm row count does not match async VLM row count")
if len(benchmark_rows) != len(vlm_rows):
    raise SystemExit("Jetson async enrichment failed: benchmark row count does not match async VLM row count")
if len(pass_rows) < required_pass_rows:
    raise SystemExit(
        f"Jetson async enrichment failed: pass rows {len(pass_rows)} < required {required_pass_rows}"
    )

summary_lines = [
    "# Jetson async VLM enrichment summary",
    "",
    f"- source_events: `{events_path}`",
    f"- async_vlm: `{vlm_path}`",
    f"- async_alarm_enriched: `{alarms_path}`",
    f"- async_benchmark_enriched: `{benchmark_path}`",
    f"- source_event_rows: {len(event_rows)}",
    f"- async_vlm_rows: {len(vlm_rows)}",
    f"- async_vlm_pass_rows: {len(pass_rows)}",
    f"- async_vlm_fallback_rows: {len(fallback_rows)}",
    f"- async_vlm_failed_rows: {len(failed_rows)}",
    f"- async_vlm_blocked_rows: {len(blocked_rows)}",
    f"- async_vlm_not_executed_rows: {len(not_executed_rows)}",
    f"- async_alarm_rows: {len(alarm_rows)}",
    f"- async_benchmark_rows: {len(benchmark_rows)}",
]
summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
PY

echo "JETSON_P7_ASYNC_VLM_RESULT=async_vlm_enrichment_smoke_pass"
echo "events_input=${EVENTS_INPUT}"
echo "async_vlm_output=${ASYNC_VLM}"
echo "async_alarm_output=${ASYNC_ALARMS}"
echo "async_benchmark_output=${ASYNC_BENCHMARK}"
echo "async_summary=${ASYNC_SUMMARY}"
echo "llm_input=${LLM_INPUT:-none}"
echo "async_vlm=${ASYNC_VLM}"
echo "async_alarm_enriched=${ASYNC_ALARMS}"
echo "async_benchmark_enriched=${ASYNC_BENCHMARK}"
echo "async_assets=${ASYNC_ASSET_DIR}"
echo "async_service_log=${ASYNC_SERVICE_LOG}"
echo "async_summary=${ASYNC_SUMMARY}"
