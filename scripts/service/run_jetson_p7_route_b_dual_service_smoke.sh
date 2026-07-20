#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-jetson_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-600}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-2}"
ASYNC_VLM_MAX_CALLS="${ASYNC_VLM_MAX_CALLS:-2}"
ASYNC_VLM_MODE="${ASYNC_VLM_MODE:-llama_cpp_multimodal_once}"
ASYNC_STOP_AFTER_BUDGET="${ASYNC_STOP_AFTER_BUDGET:-1}"
ASYNC_IDLE_TIMEOUT_SEC="${ASYNC_IDLE_TIMEOUT_SEC:-0}"
ASYNC_STARTUP_WAIT_SEC="${ASYNC_STARTUP_WAIT_SEC:-180}"
ASYNC_GRACE_SEC="${ASYNC_GRACE_SEC:-15}"
ASYNC_LAUNCH_MODE="${ASYNC_LAUNCH_MODE:-parallel}"
ASYNC_POSTRUN_COOLDOWN_SEC="${ASYNC_POSTRUN_COOLDOWN_SEC:-0}"
ASYNC_VLM_REQUIRE_PASS="${ASYNC_VLM_REQUIRE_PASS:-0}"
ASYNC_VLM_REQUIRE_PASS_ROWS="${ASYNC_VLM_REQUIRE_PASS_ROWS:-0}"
ASYNC_ASSET_SOURCE_TYPE="${ASYNC_ASSET_SOURCE_TYPE:-video_playlist}"
ASYNC_ASSET_SOURCE_URI="${ASYNC_ASSET_SOURCE_URI:-data/videos/runtime_playlist_v1.txt}"
ASYNC_ASSET_PLAYLIST_LOOP="${ASYNC_ASSET_PLAYLIST_LOOP:-1}"
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
VLM_RETRY_BACKOFF_SEC="${VLM_RETRY_BACKOFF_SEC:-0}"
VLM_ONCE_PREWARM_REQUEST="${VLM_ONCE_PREWARM_REQUEST:-0}"
VLM_ONCE_PREWARM_MAX_TOKENS="${VLM_ONCE_PREWARM_MAX_TOKENS:-0}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v1"
  exit 2
fi
if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi
if [[ "${ASYNC_LAUNCH_MODE}" != "parallel" && "${ASYNC_LAUNCH_MODE}" != "postrun" ]]; then
  echo "ASYNC_LAUNCH_MODE must be parallel or postrun, got: ${ASYNC_LAUNCH_MODE}"
  exit 2
fi

PLAYLIST="data/videos/runtime_playlist_v1.txt"
MODEL_CONFIG="projects/05_alarm_system/configs/models/jetson_model_combo.yaml"
for path in \
  "${MODEL_CONFIG}" \
  "${ASYNC_ASSET_SOURCE_URI}" \
  "${VLM_MODEL}" \
  "${MMPROJ_MODEL}" \
  "projects/05_alarm_system/scripts/service/run_async_vlm_enrichment.py" \
  "projects/05_alarm_system/scripts/service/run_jetson_p7_detector_text_resident_smoke.sh"; do
  if [[ ! -e "${path}" ]]; then
    echo "Required path is missing: ${path}"
    exit 2
  fi
done

EVENTS="benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl"
LLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl"
ASYNC_VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_outputs.jsonl"
ASYNC_ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarm_enriched.jsonl"
ASYNC_BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_enriched_benchmark.jsonl"
ASYNC_ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_assets"
ASYNC_SERVICE_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_service.log"
ASYNC_STDOUT="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_stdout.log"

mkdir -p \
  "$(dirname "${EVENTS}")" \
  "$(dirname "${ASYNC_ALARMS}")" \
  "$(dirname "${ASYNC_SERVICE_LOG}")" \
  "benchmark/processed/05_alarm_system"

rm -f \
  "${ASYNC_VLM}" \
  "${ASYNC_ALARMS}" \
  "${ASYNC_BENCHMARK}" \
  "${ASYNC_SERVICE_LOG}" \
  "${ASYNC_STDOUT}"
rm -rf "${ASYNC_ASSET_DIR}"
mkdir -p "${ASYNC_ASSET_DIR}"

ASYNC_PID=""
stop_async_worker() {
  if [[ -n "${ASYNC_PID}" ]] && kill -0 "${ASYNC_PID}" 2>/dev/null; then
    kill "${ASYNC_PID}" 2>/dev/null || true
    wait "${ASYNC_PID}" 2>/dev/null || true
  fi
  ASYNC_PID=""
}

cleanup_on_exit() {
  stop_async_worker
}

trap cleanup_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "route_b_dual_service_mode=realtime_detector_text_plus_async_vlm"
echo "detector_duration_sec=${DURATION_SEC}"
echo "text_max_calls=${TEXT_MAX_CALLS}"
echo "async_vlm_mode=${ASYNC_VLM_MODE}"
echo "async_launch_mode=${ASYNC_LAUNCH_MODE}"
echo "async_postrun_cooldown_sec=${ASYNC_POSTRUN_COOLDOWN_SEC}"
echo "async_vlm_max_calls=${ASYNC_VLM_MAX_CALLS}"
echo "async_vlm_require_pass=${ASYNC_VLM_REQUIRE_PASS}"
echo "async_vlm_require_pass_rows=${ASYNC_VLM_REQUIRE_PASS_ROWS}"
echo "vlm_retry_backoff_sec=${VLM_RETRY_BACKOFF_SEC}"
echo "vlm_once_prewarm_request=${VLM_ONCE_PREWARM_REQUEST}"
echo "vlm_once_prewarm_max_tokens=${VLM_ONCE_PREWARM_MAX_TOKENS}"

ASYNC_ARGS=(
  python3 projects/05_alarm_system/scripts/service/run_async_vlm_enrichment.py
  --run-id "${RUN_ID}"
  --board "${BOARD}"
  --environment-baseline-id "${ENV_BASELINE_ID}"
  --events-input "${EVENTS}"
  --llm-input "${LLM}"
  --model-config "${MODEL_CONFIG}"
  --asset-mode source_media
  --asset-source-type "${ASYNC_ASSET_SOURCE_TYPE}"
  --asset-source-uri "${ASYNC_ASSET_SOURCE_URI}"
  --asset-dir "${ASYNC_ASSET_DIR}"
  --asset-image-ext jpg
  --asset-jpeg-quality 85
  --vlm-mode "${ASYNC_VLM_MODE}"
  --vlm-model-path "${VLM_MODEL}"
  --mmproj-path "${MMPROJ_MODEL}"
  --llama-bin "${LLAMA_BIN_VALUE}"
  --vlm-ctx "${VLM_CTX}"
  --vlm-max-tokens "${VLM_MAX_TOKENS}"
  --vlm-timeout-ms "${VLM_TIMEOUT_MS}"
  --vlm-startup-timeout-ms "${VLM_STARTUP_TIMEOUT_MS}"
  --vlm-runtime-log-dir "logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_runtime"
  --vlm-max-calls "${ASYNC_VLM_MAX_CALLS}"
  --vlm-request-retries "${VLM_REQUEST_RETRIES}"
  --vlm-retry-backoff-sec "${VLM_RETRY_BACKOFF_SEC}"
  --vlm-once-prewarm-max-tokens "${VLM_ONCE_PREWARM_MAX_TOKENS}"
  --vlm-ngl "${VLM_NGL}"
  --vlm-image-min-tokens "${VLM_IMAGE_MIN_TOKENS}"
  --vlm-image-max-tokens "${VLM_IMAGE_MAX_TOKENS}"
  --poll-interval-sec 0.5
  --startup-wait-sec "${ASYNC_STARTUP_WAIT_SEC}"
  --idle-timeout-sec "${ASYNC_IDLE_TIMEOUT_SEC}"
  --vlm-output "${ASYNC_VLM}"
  --alarm-output "${ASYNC_ALARMS}"
  --benchmark-output "${ASYNC_BENCHMARK}"
  --service-log "${ASYNC_SERVICE_LOG}"
)

if [[ "${ASYNC_ASSET_SOURCE_TYPE}" == "video_playlist" && "${ASYNC_ASSET_PLAYLIST_LOOP}" == "1" ]]; then
  ASYNC_ARGS+=(--asset-playlist-loop)
fi
if [[ -n "${LLAMA_SERVER_BIN_VALUE}" ]]; then
  ASYNC_ARGS+=(--vlm-llama-server-bin "${LLAMA_SERVER_BIN_VALUE}")
fi
if [[ -n "${VLM_DEVICE}" ]]; then
  ASYNC_ARGS+=(--vlm-device "${VLM_DEVICE}")
fi
if [[ "${VLM_NO_MMPROJ_OFFLOAD}" == "1" ]]; then
  ASYNC_ARGS+=(--vlm-no-mmproj-offload)
fi
if [[ "${VLM_NO_KV_OFFLOAD}" == "1" ]]; then
  ASYNC_ARGS+=(--vlm-no-kv-offload)
fi
if [[ "${VLM_ONCE_PREWARM_REQUEST}" == "1" ]]; then
  ASYNC_ARGS+=(--vlm-once-prewarm-request)
fi
if [[ "${ASYNC_STOP_AFTER_BUDGET}" == "1" ]]; then
  ASYNC_ARGS+=(--stop-after-budget)
fi

launch_async_worker() {
  "${ASYNC_ARGS[@]}" > "${ASYNC_STDOUT}" 2>&1 &
  ASYNC_PID=$!
  echo "async_vlm_pid=${ASYNC_PID}"
  echo "async_vlm_stdout=${ASYNC_STDOUT}"
}

if [[ "${ASYNC_LAUNCH_MODE}" == "parallel" ]]; then
  launch_async_worker
fi

export RUN_ID BOARD ENV_BASELINE_ID DURATION_SEC TEXT_MAX_CALLS LLAMA_BIN LLAMA_SERVER_BIN
bash projects/05_alarm_system/scripts/service/run_jetson_p7_detector_text_resident_smoke.sh

if [[ "${ASYNC_LAUNCH_MODE}" == "postrun" ]]; then
  if [[ "${ASYNC_POSTRUN_COOLDOWN_SEC}" != "0" && "${ASYNC_POSTRUN_COOLDOWN_SEC}" != "0.0" ]]; then
    echo "async_postrun_cooldown_sleep=${ASYNC_POSTRUN_COOLDOWN_SEC}"
    sleep "${ASYNC_POSTRUN_COOLDOWN_SEC}"
  fi
  launch_async_worker
  if [[ -n "${ASYNC_PID}" ]]; then
    wait "${ASYNC_PID}"
    ASYNC_PID=""
  fi
elif [[ -n "${ASYNC_PID}" ]] && kill -0 "${ASYNC_PID}" 2>/dev/null; then
  sleep "${ASYNC_GRACE_SEC}"
  stop_async_worker
fi

if [[ -s "${ASYNC_ALARMS}" ]]; then
  python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
    --input "${ASYNC_ALARMS}" \
    --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
    --output "benchmark/processed/05_alarm_system/${RUN_ID}_async_alarm_schema_check.md"
fi

if [[ -s "${ASYNC_BENCHMARK}" ]]; then
  python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
    --input "${ASYNC_BENCHMARK}" \
    --schema benchmark/schemas/alarm_system_raw_schema.json \
    --output "benchmark/processed/05_alarm_system/${RUN_ID}_async_benchmark_schema_check.md"
fi

python3 - "${ASYNC_VLM}" "${ASYNC_VLM_REQUIRE_PASS}" "${ASYNC_VLM_REQUIRE_PASS_ROWS}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
require_pass = int(sys.argv[2])
require_pass_rows = int(sys.argv[3])
required = max(require_pass_rows, 1 if require_pass else 0)
if not path.exists() or path.stat().st_size == 0:
    raise SystemExit("Route B dual-service async VLM failed: no async VLM rows were produced")
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
pass_rows = [row for row in rows if row.get("status") == "pass"]
fallback_rows = [row for row in rows if row.get("status") == "fallback"]
failed_rows = [row for row in rows if row.get("status") == "failed"]
blocked_rows = [row for row in rows if row.get("status") == "blocked_no_image_asset"]
unknown_rows = [
    row for row in rows
    if row.get("status") not in {"pass", "fallback", "failed", "blocked_no_image_asset", "not_executed"}
]
print(f"async_vlm_rows={len(rows)}")
print(f"async_vlm_pass_rows={len(pass_rows)}")
print(f"async_vlm_fallback_rows={len(fallback_rows)}")
print(f"async_vlm_failed_rows={len(failed_rows)}")
print(f"async_vlm_blocked_rows={len(blocked_rows)}")
if unknown_rows:
    for row in unknown_rows[:5]:
        print(f"async_vlm_unknown_event={row.get('event_id')} status={row.get('status')} mode={row.get('mode')}")
    raise SystemExit("Route B dual-service async VLM failed: unexpected async VLM row status")
if len(pass_rows) < required:
    raise SystemExit(
        f"Route B dual-service async VLM failed: pass_rows={len(pass_rows)} < required={required}"
    )
PY

echo "JETSON_ROUTE_B_DUAL_SERVICE_RESULT=realtime_detector_text_plus_async_vlm_worker_ready"
echo "events=${EVENTS}"
echo "llm=${LLM}"
echo "async_vlm=${ASYNC_VLM}"
echo "async_alarm_enriched=${ASYNC_ALARMS}"
echo "async_benchmark_enriched=${ASYNC_BENCHMARK}"
echo "async_assets=${ASYNC_ASSET_DIR}"
echo "async_service_log=${ASYNC_SERVICE_LOG}"
echo "async_stdout=${ASYNC_STDOUT}"
