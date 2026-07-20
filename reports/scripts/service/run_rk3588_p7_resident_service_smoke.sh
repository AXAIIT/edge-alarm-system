#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-rk3588_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260611_rk3588_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-600}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-2}"
VLM_MAX_CALLS="${VLM_MAX_CALLS:-2}"
FRAME_CACHE_CAPACITY="${FRAME_CACHE_CAPACITY:-512}"
FRAME_CACHE_JPEG_QUALITY="${FRAME_CACHE_JPEG_QUALITY:-85}"
SERVICE_QUEUE_CAPACITY="${SERVICE_QUEUE_CAPACITY:-32}"
DETECTOR_QUEUE_CAPACITY="${DETECTOR_QUEUE_CAPACITY:-16}"
CLEAN_FRAME_CACHE_ON_EXIT="${CLEAN_FRAME_CACHE_ON_EXIT:-1}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260712_rk3588_8gb_alarm_service_resident_concurrency_smoke_v1"
  exit 2
fi
if [[ "${BOARD}" != "rk3588_8gb" ]]; then
  echo "BOARD must be rk3588_8gb, got: ${BOARD}"
  exit 2
fi

RUNNER="projects/05_alarm_system/runners/detector/rk3588_yolo11n_detector_service"
TEXT_RUNNER="projects/05_alarm_system/runners/rkllm_resident_text_server/build/rkllm_resident_text_server"
VLM_RUNNER="projects/05_alarm_system/runners/rkllm_resident_vlm_server/build/rkllm_resident_vlm_server"
TEXT_MODEL="models/llm_vlm/Qwen3-1.7B-RKLLM/qwen3_1_7b.rkllm"
VISION_MODEL="models/llm_vlm/Qwen3-VL-2B-RKNN/qwen3-vl_vision_384_patch_embed_cpu_rk3588.rknn"
DECODER_MODEL="models/llm_vlm/Qwen3-VL-2B-RKLLM/qwen3-vl-2b-instruct_w8a8_rk3588.rkllm"
PLAYLIST="data/videos/runtime_playlist_v1.txt"

for path in \
  "${RUNNER}" \
  "${TEXT_RUNNER}" \
  "${VLM_RUNNER}" \
  "${TEXT_MODEL}" \
  "${VISION_MODEL}" \
  "${DECODER_MODEL}" \
  "${PLAYLIST}" \
  "projects/05_alarm_system/configs/detector/pipeline/rk3588_rknn_pipeline.yaml" \
  "projects/05_alarm_system/configs/detector/models/yolo11n.yaml" \
  "projects/05_alarm_system/configs/detector/boards/rk3588_8gb.yaml" \
  "projects/05_alarm_system/configs/inputs/video_sources.yaml" \
  "projects/05_alarm_system/configs/event_rules/rk3588_rules.yaml" \
  "projects/05_alarm_system/configs/models/rk3588_model_combo.yaml"; do
  if [[ ! -e "${path}" ]]; then
    echo "Required path is missing: ${path}"
    exit 2
  fi
done
for bin in "${RUNNER}" "${TEXT_RUNNER}" "${VLM_RUNNER}"; do
  if [[ ! -x "${bin}" ]]; then
    echo "Executable is required: ${bin}"
    exit 2
  fi
done

FRAME_CACHE_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_frame_cache"
ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_assets"
DETECTOR_OUT="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.jsonl"
DETECTOR_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.log"
MONITOR_LOG="logs/monitor/05_alarm_system/${BOARD}/${RUN_ID}_rknpu_monitor.log"
SERVICE_STDOUT="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service_stdout.log"
SERVICE_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service.log"
TEXT_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_rkllm_runtime"
VLM_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_vlm_runtime"
VLM_METRICS_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_vlm_metrics"
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
  "${VLM_RUNTIME_DIR}" \
  "${VLM_METRICS_DIR}"

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
rm -rf "${FRAME_CACHE_DIR}" "${ASSET_DIR}" "${TEXT_RUNTIME_DIR}" "${VLM_RUNTIME_DIR}" "${VLM_METRICS_DIR}"
mkdir -p "${FRAME_CACHE_DIR}" "${ASSET_DIR}" "${TEXT_RUNTIME_DIR}" "${VLM_RUNTIME_DIR}" "${VLM_METRICS_DIR}"

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
  "--config" "projects/05_alarm_system/configs/detector/pipeline/rk3588_rknn_pipeline.yaml"
  "--model-config" "projects/05_alarm_system/configs/detector/models/yolo11n.yaml"
  "--backend-config" "projects/05_alarm_system/configs/detector/boards/rk3588_8gb.yaml"
  "--stream-config" "projects/05_alarm_system/configs/inputs/video_sources.yaml"
  "--input-source-id" "video_set_runtime_v1"
  "--input-source-type" "video_playlist"
  "--input" "${PLAYLIST}"
  "--duration-sec" "${DURATION_SEC}"
  "--raw-output" "${DETECTOR_OUT}"
  "--runtime-log" "${DETECTOR_LOG}"
  "--preview-window" "off"
  "--inference-workers" "3"
  "--rknn-core-mask" "0_1_2"
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
echo "detector_start_order=after_workers"
echo "frame_cache_capacity=${FRAME_CACHE_CAPACITY}"
echo "service_queue_capacity=${SERVICE_QUEUE_CAPACITY}"
echo "detector_queue_capacity=${DETECTOR_QUEUE_CAPACITY}"

INTERVAL_SEC=1 APP_MATCH_PATTERN="projects/05_alarm_system" \
  bash projects/05_alarm_system/scripts/monitor/monitor_rk3588_rknpu.sh "${MONITOR_LOG}" &
MONITOR_PID=$!

P7_START_EPOCH=$(date +%s)
python3 projects/05_alarm_system/scripts/service/run_alarm_service.py \
  --run-id "${RUN_ID}" \
  --board "${BOARD}" \
  --board-name "RK3588 8GB" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --detector-mode resident_process \
  --detector-command "${DETECTOR_CMD}" \
  --detector-output "${DETECTOR_OUT}" \
  --detector-runtime-log "${DETECTOR_LOG}" \
  --detector-start-order after_workers \
  --rules projects/05_alarm_system/configs/event_rules/rk3588_rules.yaml \
  --model-config projects/05_alarm_system/configs/models/rk3588_model_combo.yaml \
  --asset-mode source_media \
  --asset-source-type frame_cache_dir \
  --asset-source-uri "${FRAME_CACHE_DIR}" \
  --asset-dir "${ASSET_DIR}" \
  --asset-trigger-policy vlm_real_calls_only \
  --queue-capacity "${SERVICE_QUEUE_CAPACITY}" \
  --stability-tier smoke \
  --window-sec "${DURATION_SEC}" \
  --monitor-log "${MONITOR_LOG}" \
  --text-mode rkllm_resident \
  --text-model-path "${TEXT_MODEL}" \
  --rkllm-runner "${TEXT_RUNNER}" \
  --text-ctx 2048 \
  --text-max-tokens 128 \
  --text-timeout-ms 60000 \
  --text-startup-timeout-ms 30000 \
  --text-runtime-log-dir "${TEXT_RUNTIME_DIR}" \
  --text-max-calls "${TEXT_MAX_CALLS}" \
  --vlm-mode rkllm_multimodal_resident \
  --rkllm-mm-resident-runner "${VLM_RUNNER}" \
  --vision-model "${VISION_MODEL}" \
  --decoder-model "${DECODER_MODEL}" \
  --vlm-ctx 2048 \
  --vlm-max-tokens 256 \
  --vlm-timeout-ms 70000 \
  --vlm-startup-timeout-ms 30000 \
  --vlm-runtime-log-dir "${VLM_RUNTIME_DIR}" \
  --vlm-metrics-dir "${VLM_METRICS_DIR}" \
  --vlm-max-calls "${VLM_MAX_CALLS}" \
  --status not_verified \
  --service-status stopped \
  2>&1 | tee "${SERVICE_STDOUT}"
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
