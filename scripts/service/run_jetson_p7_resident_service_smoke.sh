#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-jetson_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-600}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-2}"
VLM_MAX_CALLS="${VLM_MAX_CALLS:-2}"
FRAME_CACHE_CAPACITY="${FRAME_CACHE_CAPACITY:-1536}"
FRAME_CACHE_JPEG_QUALITY="${FRAME_CACHE_JPEG_QUALITY:-85}"
SERVICE_QUEUE_CAPACITY="${SERVICE_QUEUE_CAPACITY:-192}"
DETECTOR_QUEUE_CAPACITY="${DETECTOR_QUEUE_CAPACITY:-8}"
DETECTOR_STARTUP_TIMEOUT_SEC="${DETECTOR_STARTUP_TIMEOUT_SEC:-90}"
DETECTOR_POLL_INTERVAL_SEC="${DETECTOR_POLL_INTERVAL_SEC:-0.2}"
DETECTOR_START_RETRIES="${DETECTOR_START_RETRIES:-2}"
DETECTOR_RESTART_DELAY_SEC="${DETECTOR_RESTART_DELAY_SEC:-8}"
DETECTOR_START_ORDER="${DETECTOR_START_ORDER:-after_workers}"
TEXT_MODEL="${TEXT_MODEL:-${QWEN3_GGUF:-models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf}}"
VLM_MODEL="${VLM_MODEL:-${QWEN3_VL_GGUF:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf}}"
MMPROJ_MODEL="${MMPROJ_MODEL:-${QWEN3_VL_MMPROJ:-models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf}}"
LLAMA_BIN_VALUE="${LLAMA_BIN:-llama-cli}"
LLAMA_SERVER_BIN_VALUE="${LLAMA_SERVER_BIN:-}"
TEXT_CTX="${TEXT_CTX:-2048}"
TEXT_MAX_TOKENS="${TEXT_MAX_TOKENS:-64}"
TEXT_TIMEOUT_MS="${TEXT_TIMEOUT_MS:-180000}"
TEXT_STARTUP_TIMEOUT_MS="${TEXT_STARTUP_TIMEOUT_MS:-90000}"
TEXT_NGL="${TEXT_NGL:-0}"
TEXT_NO_KV_OFFLOAD="${TEXT_NO_KV_OFFLOAD:-1}"
TEXT_DEVICE="${TEXT_DEVICE:-none}"
QWEN_NO_THINK="${QWEN_NO_THINK:-1}"
VLM_CTX="${VLM_CTX:-1536}"
VLM_MAX_TOKENS="${VLM_MAX_TOKENS:-64}"
VLM_TIMEOUT_MS="${VLM_TIMEOUT_MS:-210000}"
VLM_STARTUP_TIMEOUT_MS="${VLM_STARTUP_TIMEOUT_MS:-120000}"
VLM_NGL="${VLM_NGL:-0}"
VLM_DEVICE="${VLM_DEVICE:-}"
VLM_IMAGE_MIN_TOKENS="${VLM_IMAGE_MIN_TOKENS:-512}"
VLM_IMAGE_MAX_TOKENS="${VLM_IMAGE_MAX_TOKENS:-512}"
VLM_NO_MMPROJ_OFFLOAD="${VLM_NO_MMPROJ_OFFLOAD:-1}"
VLM_NO_KV_OFFLOAD="${VLM_NO_KV_OFFLOAD:-1}"
VLM_REQUEST_RETRIES="${VLM_REQUEST_RETRIES:-1}"
CLEAN_FRAME_CACHE_ON_EXIT="${CLEAN_FRAME_CACHE_ON_EXIT:-1}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v1"
  exit 2
fi
if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi

RUNNER="projects/05_alarm_system/runners/detector/jetson_yolo11n_detector_service"
PLAYLIST="data/videos/runtime_playlist_v1.txt"
for path in \
  "${RUNNER}" \
  "${PLAYLIST}" \
  "${TEXT_MODEL}" \
  "${VLM_MODEL}" \
  "${MMPROJ_MODEL}" \
  "projects/05_alarm_system/configs/detector/pipeline/jetson_tensorrt_pipeline.yaml" \
  "projects/05_alarm_system/configs/detector/models/yolo11n.yaml" \
  "projects/05_alarm_system/configs/detector/boards/jetson_8gb.yaml" \
  "projects/05_alarm_system/configs/inputs/video_sources.yaml" \
  "projects/05_alarm_system/configs/event_rules/jetson_rules.yaml" \
  "projects/05_alarm_system/configs/models/jetson_model_combo.yaml"; do
  if [[ ! -e "${path}" ]]; then
    echo "Required path is missing: ${path}"
    exit 2
  fi
done
if [[ ! -x "${RUNNER}" ]]; then
  echo "Executable is required: ${RUNNER}"
  exit 2
fi
if ! command -v tegrastats >/dev/null 2>&1; then
  echo "tegrastats is required in PATH"
  exit 2
fi

FRAME_CACHE_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_frame_cache"
ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_assets"
DETECTOR_OUT="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.jsonl"
DETECTOR_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.log"
MONITOR_LOG="logs/monitor/05_alarm_system/${BOARD}/${RUN_ID}_tegrastats.log"
SERVICE_STDOUT="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service_stdout.log"
SERVICE_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service.log"
TEXT_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_cpp_text_runtime"
VLM_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_cpp_vlm_runtime"
EVENTS="benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl"
LLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl"
VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl"
ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl"
BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl"
STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"

mkdir -p \
  "$(dirname "${DETECTOR_OUT}")" \
  "$(dirname "${DETECTOR_LOG}")" \
  "$(dirname "${MONITOR_LOG}")" \
  "$(dirname "${SERVICE_STDOUT}")" \
  "$(dirname "${EVENTS}")" \
  "$(dirname "${ALARMS}")" \
  benchmark/processed/05_alarm_system \
  "${TEXT_RUNTIME_DIR}" \
  "${VLM_RUNTIME_DIR}"

rm -f \
  "${DETECTOR_OUT}" \
  "${DETECTOR_LOG}" \
  "${MONITOR_LOG}" \
  "${SERVICE_STDOUT}" \
  "${SERVICE_LOG}" \
  "${EVENTS}" \
  "${LLM}" \
  "${VLM}" \
  "${ALARMS}" \
  "${BENCHMARK}" \
  "${STABILITY}"
rm -rf "${FRAME_CACHE_DIR}" "${ASSET_DIR}" "${TEXT_RUNTIME_DIR}" "${VLM_RUNTIME_DIR}"
mkdir -p "${FRAME_CACHE_DIR}" "${ASSET_DIR}" "${TEXT_RUNTIME_DIR}" "${VLM_RUNTIME_DIR}"

quote_join() {
  local joined=""
  local q=""
  for arg in "$@"; do
    printf -v q '%q' "${arg}"
    joined+="${q} "
  done
  printf '%s' "${joined% }"
}

DETECTOR_CMD_PARTS=(
  "${RUNNER}"
  "--config" "projects/05_alarm_system/configs/detector/pipeline/jetson_tensorrt_pipeline.yaml"
  "--model-config" "projects/05_alarm_system/configs/detector/models/yolo11n.yaml"
  "--backend-config" "projects/05_alarm_system/configs/detector/boards/jetson_8gb.yaml"
  "--stream-config" "projects/05_alarm_system/configs/inputs/video_sources.yaml"
  "--input-source-id" "video_set_runtime_v1"
  "--input-source-type" "video_playlist"
  "--input" "${PLAYLIST}"
  "--duration-sec" "${DURATION_SEC}"
  "--raw-output" "${DETECTOR_OUT}"
  "--runtime-log" "${DETECTOR_LOG}"
  "--preview-window" "off"
  "--inference-workers" "1"
  "--queue-capacity" "${DETECTOR_QUEUE_CAPACITY}"
  "--queue-push-timeout-ms" "20"
  "--frame-cache-dir" "${FRAME_CACHE_DIR}"
  "--frame-cache-capacity" "${FRAME_CACHE_CAPACITY}"
  "--frame-cache-jpeg-quality" "${FRAME_CACHE_JPEG_QUALITY}"
)
DETECTOR_CMD="$(quote_join "${DETECTOR_CMD_PARTS[@]}")"

MONITOR_PID=""
stop_monitor() {
  if [[ -n "${MONITOR_PID}" ]] && kill -0 "${MONITOR_PID}" 2>/dev/null; then
    kill "${MONITOR_PID}" 2>/dev/null || true
    wait "${MONITOR_PID}" 2>/dev/null || true
  fi
  MONITOR_PID=""
}

cleanup_frame_cache() {
  if [[ "${CLEAN_FRAME_CACHE_ON_EXIT}" == "1" && -d "${FRAME_CACHE_DIR}" ]]; then
    rm -rf "${FRAME_CACHE_DIR}"
    echo "frame_cache_cleanup=done"
  fi
}

cleanup_on_exit() {
  stop_monitor
  cleanup_frame_cache
}

trap cleanup_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "resident_service_smoke_mode=resident_detector_plus_resident_text_vlm"
echo "detector_duration_sec=${DURATION_SEC}"
echo "text_max_calls=${TEXT_MAX_CALLS}"
echo "vlm_max_calls=${VLM_MAX_CALLS}"
echo "detector_start_retries=${DETECTOR_START_RETRIES}"
echo "detector_restart_delay_sec=${DETECTOR_RESTART_DELAY_SEC}"
echo "detector_start_order=${DETECTOR_START_ORDER}"
echo "text_ngl=${TEXT_NGL}"
echo "text_no_kv_offload=${TEXT_NO_KV_OFFLOAD}"
echo "text_device=${TEXT_DEVICE}"
echo "qwen_no_think=${QWEN_NO_THINK}"
echo "vlm_ngl=${VLM_NGL}"
echo "vlm_device=${VLM_DEVICE:-auto}"
echo "vlm_no_mmproj_offload=${VLM_NO_MMPROJ_OFFLOAD}"
echo "vlm_no_kv_offload=${VLM_NO_KV_OFFLOAD}"
echo "vlm_request_retries=${VLM_REQUEST_RETRIES}"
echo "frame_cache_capacity=${FRAME_CACHE_CAPACITY}"
echo "service_queue_capacity=${SERVICE_QUEUE_CAPACITY}"
echo "detector_queue_capacity=${DETECTOR_QUEUE_CAPACITY}"

tegrastats --interval 1000 --logfile "${MONITOR_LOG}" &
MONITOR_PID=$!

ARGS=(
  python3 projects/05_alarm_system/scripts/service/run_alarm_service.py
  --run-id "${RUN_ID}"
  --board "${BOARD}"
  --board-name "Jetson Xavier NX 8GB"
  --environment-baseline-id "${ENV_BASELINE_ID}"
  --detector-mode resident_process
  --detector-command "${DETECTOR_CMD}"
  --detector-output "${DETECTOR_OUT}"
  --detector-runtime-log "${DETECTOR_LOG}"
  --detector-start-order "${DETECTOR_START_ORDER}"
  --detector-startup-timeout-sec "${DETECTOR_STARTUP_TIMEOUT_SEC}"
  --detector-poll-interval-sec "${DETECTOR_POLL_INTERVAL_SEC}"
  --detector-start-retries "${DETECTOR_START_RETRIES}"
  --detector-restart-delay-sec "${DETECTOR_RESTART_DELAY_SEC}"
  --rules projects/05_alarm_system/configs/event_rules/jetson_rules.yaml
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml
  --asset-mode source_media
  --asset-source-type frame_cache_dir
  --asset-source-uri "${FRAME_CACHE_DIR}"
  --asset-dir "${ASSET_DIR}"
  --asset-trigger-policy vlm_real_calls_only
  --queue-capacity "${SERVICE_QUEUE_CAPACITY}"
  --stability-tier smoke
  --window-sec "${DURATION_SEC}"
  --monitor-log "${MONITOR_LOG}"
  --text-mode llama_cpp_resident
  --text-model-path "${TEXT_MODEL}"
  --llama-bin "${LLAMA_BIN_VALUE}"
  --text-ctx "${TEXT_CTX}"
  --text-max-tokens "${TEXT_MAX_TOKENS}"
  --text-timeout-ms "${TEXT_TIMEOUT_MS}"
  --text-startup-timeout-ms "${TEXT_STARTUP_TIMEOUT_MS}"
  --text-runtime-log-dir "${TEXT_RUNTIME_DIR}"
  --text-max-calls "${TEXT_MAX_CALLS}"
  --text-device "${TEXT_DEVICE}"
  --vlm-mode llama_cpp_multimodal_resident
  --vlm-model-path "${VLM_MODEL}"
  --mmproj-path "${MMPROJ_MODEL}"
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
  --status not_verified
  --service-status stopped
)

if [[ -n "${LLAMA_SERVER_BIN_VALUE}" ]]; then
  ARGS+=(--llama-server-bin "${LLAMA_SERVER_BIN_VALUE}")
fi
if [[ -n "${TEXT_NGL}" ]]; then
  ARGS+=(--ngl "${TEXT_NGL}")
fi
if [[ "${TEXT_NO_KV_OFFLOAD}" == "1" ]]; then
  ARGS+=(--text-no-kv-offload)
fi
if [[ "${QWEN_NO_THINK}" == "1" ]]; then
  ARGS+=(--qwen-no-think)
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

P7_START_EPOCH=$(date +%s)
"${ARGS[@]}" 2>&1 | tee "${SERVICE_STDOUT}"
SERVICE_EXIT=${PIPESTATUS[0]}
P7_END_EPOCH=$(date +%s)
P7_ELAPSED_SEC=$((P7_END_EPOCH - P7_START_EPOCH))
stop_monitor

echo "SERVICE_EXIT=${SERVICE_EXIT}"
echo "P7_ELAPSED_SEC=${P7_ELAPSED_SEC}"
if [[ "${SERVICE_EXIT}" -ne 0 ]]; then
  echo "P7 failed: service returned ${SERVICE_EXIT}"
  echo "service_stdout=${SERVICE_STDOUT}"
  echo "detector_log=${DETECTOR_LOG}"
  exit "${SERVICE_EXIT}"
fi
if [[ "${P7_ELAPSED_SEC}" -lt "${DURATION_SEC}" ]]; then
  echo "P7 failed: wall-clock duration is shorter than ${DURATION_SEC} seconds"
  exit 1
fi
if [[ ! -s "${MONITOR_LOG}" ]]; then
  echo "P7 failed: monitor log is missing or empty"
  exit 1
fi

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${EVENTS}" \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_service_event_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${ALARMS}" \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_service_alarm_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${BENCHMARK}" \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_service_raw_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${STABILITY}" \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_service_stability_schema_check.md" || exit $?

python3 - "${STABILITY}" "${TEXT_MAX_CALLS}" "${VLM_MAX_CALLS}" <<'PY'
import json
import sys

path, expected_text_calls, expected_vlm_calls = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
with open(path, encoding="utf-8") as handle:
    row = json.loads(handle.readline())
for key in (
    "window_sec",
    "requested_window_sec",
    "window_requirement_met",
    "detection_fps",
    "event_count",
    "alarm_count",
    "llm_call_count",
    "vlm_call_count",
    "event_queue_depth",
    "drop_count",
    "status",
    "service_status",
):
    print(f"{key}={row.get(key)}")
if row.get("window_requirement_met") is not True:
    raise SystemExit("P7 failed: requested wall-clock duration was not met")
if not row.get("event_count") or not row.get("alarm_count"):
    raise SystemExit("P7 failed: no event/alarm evidence was produced")
if row.get("llm_call_count") != expected_text_calls:
    raise SystemExit(f"P7 failed: llm_call_count != {expected_text_calls}")
if row.get("vlm_call_count") != expected_vlm_calls:
    raise SystemExit(f"P7 failed: vlm_call_count != {expected_vlm_calls}")
PY

python3 - "${LLM}" "${TEXT_MAX_CALLS}" <<'PY'
import json
import sys

path, expected = sys.argv[1], int(sys.argv[2])
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
pass_rows = [r for r in rows if r.get("status") == "pass"]
bad_rows = [
    r for r in rows
    if r.get("status") not in {"pass", "stub"}
    or (r.get("status") == "stub" and "budget_exhausted" not in str(r.get("mode", "")))
]
print(f"llm_rows={len(rows)}")
print(f"llm_pass_rows={len(pass_rows)}")
print(f"llm_bad_rows={len(bad_rows)}")
if len(pass_rows) != expected:
    raise SystemExit(f"P7 failed: expected {expected} resident text pass rows")
if bad_rows:
    raise SystemExit("P7 failed: unexpected LLM row status/mode")
pids = sorted({r.get('resident_server_pid') for r in pass_rows if r.get('resident_server_pid') is not None})
loads = sorted({r.get('resident_model_load_count') for r in pass_rows if r.get('resident_model_load_count') is not None})
indexes = [r.get('resident_request_index') for r in pass_rows]
print(f"llm_resident_server_pids={pids}")
print(f"llm_resident_model_load_counts={loads}")
print(f"llm_resident_request_indexes={indexes}")
if len(pids) != 1 or loads != [1]:
    raise SystemExit("P7 failed: resident text pid/load_count mismatch")
if indexes != sorted(indexes):
    raise SystemExit("P7 failed: resident text request indexes are not monotonic")
PY

python3 - "${VLM}" "${VLM_MAX_CALLS}" <<'PY'
import json
import sys

path, expected = sys.argv[1], int(sys.argv[2])
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
pass_rows = [r for r in rows if r.get("status") == "pass"]
bad_rows = [
    r for r in rows
    if r.get("status") not in {"pass", "not_executed"}
    or (r.get("status") == "not_executed" and "budget_exhausted" not in str(r.get("mode", "")))
]
print(f"vlm_rows={len(rows)}")
print(f"vlm_pass_rows={len(pass_rows)}")
print(f"vlm_bad_rows={len(bad_rows)}")
if bad_rows:
    for row in bad_rows[:5]:
        print(
            "vlm_bad_event="
            f"{row.get('event_id')} status={row.get('status')} mode={row.get('mode')} "
            f"image_path={row.get('image_path')} image_source_field={row.get('image_source_field')} "
            f"metrics_error={row.get('metrics_error')}"
        )
if len(pass_rows) != expected:
    raise SystemExit(f"P7 failed: expected {expected} resident VLM pass rows")
if bad_rows:
    raise SystemExit("P7 failed: unexpected VLM row status/mode")
pids = sorted({r.get('resident_server_pid') for r in pass_rows if r.get('resident_server_pid') is not None})
loads = sorted({r.get('resident_model_load_count') for r in pass_rows if r.get('resident_model_load_count') is not None})
indexes = [r.get('resident_request_index') for r in pass_rows]
print(f"vlm_resident_server_pids={pids}")
print(f"vlm_resident_model_load_counts={loads}")
print(f"vlm_resident_request_indexes={indexes}")
if len(pids) != 1 or loads != [1]:
    raise SystemExit("P7 failed: resident VLM pid/load_count mismatch")
if indexes != sorted(indexes):
    raise SystemExit("P7 failed: resident VLM request indexes are not monotonic")
PY

echo "P7_RESULT=resident_service_smoke_pass_with_resident_text_vlm_workers"
echo "events=${EVENTS}"
echo "llm=${LLM}"
echo "vlm=${VLM}"
echo "alarms=${ALARMS}"
echo "benchmark=${BENCHMARK}"
echo "stability=${STABILITY}"
echo "service_log=${SERVICE_LOG}"
echo "service_stdout=${SERVICE_STDOUT}"
echo "detector_log=${DETECTOR_LOG}"
echo "monitor_log=${MONITOR_LOG}"
