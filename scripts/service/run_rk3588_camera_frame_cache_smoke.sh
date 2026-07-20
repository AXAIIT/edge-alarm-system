#!/usr/bin/env bash
set -uo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-rk3588_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260611_rk3588_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-300}"
SOURCE_ID="${SOURCE_ID:-astra_s_openni_001}"
SOURCE_TYPE="${SOURCE_TYPE:-openni_camera}"
SOURCE_INPUT="${SOURCE_INPUT:-2bc5/0402}"
MAX_EVENTS="${MAX_EVENTS:-3}"
FRAME_CACHE_CAPACITY="${FRAME_CACHE_CAPACITY:-256}"
FRAME_CACHE_JPEG_QUALITY="${FRAME_CACHE_JPEG_QUALITY:-85}"
CLEAN_FRAME_CACHE_ON_EXIT="${CLEAN_FRAME_CACHE_ON_EXIT:-1}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260711_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1"
  exit 2
fi
if [[ "${BOARD}" != "rk3588_8gb" ]]; then
  echo "BOARD must be rk3588_8gb, got: ${BOARD}"
  exit 2
fi

RUNNER="projects/05_alarm_system/runners/detector/rk3588_yolo11n_detector_service"
for path in \
  "${RUNNER}" \
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
if [[ ! -x "${RUNNER}" ]]; then
  echo "Detector runner is not executable: ${RUNNER}"
  exit 2
fi

FRAME_CACHE_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_frame_cache"
DETECTOR_OUT="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.jsonl"
DETECTOR_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.log"
SERVICE_STDOUT="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service_stdout.log"
SERVICE_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service.log"
EVENTS="benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl"
LLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl"
VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl"
ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl"
BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl"
STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"
ASSET_DIR="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_assets"

mkdir -p \
  "$(dirname "${DETECTOR_OUT}")" \
  "$(dirname "${DETECTOR_LOG}")" \
  "$(dirname "${SERVICE_STDOUT}")" \
  "$(dirname "${EVENTS}")" \
  "$(dirname "${ALARMS}")" \
  "$(dirname "${STABILITY}")" \
  benchmark/processed/05_alarm_system

rm -f \
  "${DETECTOR_OUT}" \
  "${DETECTOR_LOG}" \
  "${SERVICE_STDOUT}" \
  "${SERVICE_LOG}" \
  "${EVENTS}" \
  "${LLM}" \
  "${VLM}" \
  "${ALARMS}" \
  "${BENCHMARK}" \
  "${STABILITY}"
rm -rf "${FRAME_CACHE_DIR}" "${ASSET_DIR}"
mkdir -p "${FRAME_CACHE_DIR}" "${ASSET_DIR}"

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
  "--input-source-id" "${SOURCE_ID}"
  "--input-source-type" "${SOURCE_TYPE}"
  "--input" "${SOURCE_INPUT}"
  "--duration-sec" "${DURATION_SEC}"
  "--raw-output" "${DETECTOR_OUT}"
  "--runtime-log" "${DETECTOR_LOG}"
  "--preview-window" "off"
  "--inference-workers" "3"
  "--rknn-core-mask" "0_1_2"
  "--queue-capacity" "8"
  "--queue-push-timeout-ms" "20"
  "--frame-cache-dir" "${FRAME_CACHE_DIR}"
  "--frame-cache-capacity" "${FRAME_CACHE_CAPACITY}"
  "--frame-cache-jpeg-quality" "${FRAME_CACHE_JPEG_QUALITY}"
)
DETECTOR_CMD="$(quote_join "${DETECTOR_CMD_PARTS[@]}")"

echo "camera_frame_cache_smoke_mode=asset_path_validation"
echo "smoke_stop_condition=max_events_or_detector_exit max_events=${MAX_EVENTS} detector_duration_sec=${DURATION_SEC}"

python3 projects/05_alarm_system/scripts/service/run_alarm_service.py \
  --run-id "${RUN_ID}" \
  --board "${BOARD}" \
  --board-name "RK3588 8GB" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --detector-mode resident_process \
  --detector-command "${DETECTOR_CMD}" \
  --detector-output "${DETECTOR_OUT}" \
  --detector-runtime-log "${DETECTOR_LOG}" \
  --rules projects/05_alarm_system/configs/event_rules/rk3588_rules.yaml \
  --model-config projects/05_alarm_system/configs/models/rk3588_model_combo.yaml \
  --asset-mode source_media \
  --asset-source-type frame_cache_dir \
  --asset-source-uri "${FRAME_CACHE_DIR}" \
  --asset-dir "${ASSET_DIR}" \
  --text-mode template \
  --text-max-calls 0 \
  --vlm-mode stub \
  --vlm-max-calls 0 \
  --max-events "${MAX_EVENTS}" \
  --status not_verified \
  --service-status stopped \
  2>&1 | tee "${SERVICE_STDOUT}"
SERVICE_EXIT=${PIPESTATUS[0]}

echo "SERVICE_EXIT=${SERVICE_EXIT}"
if [[ "${SERVICE_EXIT}" -ne 0 ]]; then
  echo "camera frame-cache smoke failed: service returned ${SERVICE_EXIT}"
  echo "service_stdout=${SERVICE_STDOUT}"
  echo "detector_log=${DETECTOR_LOG}"
  exit "${SERVICE_EXIT}"
fi

EVENT_ROWS=0
if [[ -f "${EVENTS}" ]]; then
  EVENT_ROWS=$(wc -l < "${EVENTS}")
fi

echo "event_rows=${EVENT_ROWS}"
echo "frame_cache_dir=${FRAME_CACHE_DIR}"
echo "service_log=${SERVICE_LOG}"
echo "detector_log=${DETECTOR_LOG}"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${STABILITY}" \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_camera_frame_cache_stability_schema_check.md" || exit $?

if [[ "${EVENT_ROWS}" -gt 0 ]]; then
  python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
    --input "${EVENTS}" \
    --schema benchmark/schemas/alarm_event_package_schema.json \
    --output "benchmark/processed/05_alarm_system/${RUN_ID}_camera_frame_cache_event_schema_check.md" || exit $?
  echo "CAMERA_FRAME_CACHE_RESULT=camera_frame_cache_asset_smoke_pass"
else
  echo "CAMERA_FRAME_CACHE_RESULT=camera_frame_cache_input_pass_no_alarm_event"
fi

if [[ "${CLEAN_FRAME_CACHE_ON_EXIT}" == "1" ]]; then
  rm -rf "${FRAME_CACHE_DIR}"
  echo "frame_cache_cleanup=done"
fi
