#!/usr/bin/env bash
# Run the Jetson Project5 P4 detector-resident smoke in the foreground.
set -uo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-jetson_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-600}"
DETECTOR_STARTUP_TIMEOUT_SEC="${DETECTOR_STARTUP_TIMEOUT_SEC:-90}"
DETECTOR_POLL_INTERVAL_SEC="${DETECTOR_POLL_INTERVAL_SEC:-0.2}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1"
  exit 2
fi
if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi

RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}"
STATUS_FILE="${RUNTIME_DIR}/${RUN_ID}_p4_status.env"
mkdir -p "${RUNTIME_DIR}"

write_preflight_failure() {
  local reason="$1"
  local temp_file="${STATUS_FILE}.tmp"
  {
    echo "state=failed"
    echo "run_id=${RUN_ID}"
    echo "pid=$$"
    echo "exit_code=2"
    echo "failure_phase=preflight"
    echo "failure_reason=${reason}"
    echo "updated_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "${temp_file}"
  mv "${temp_file}" "${STATUS_FILE}"
}

fail_preflight() {
  local reason="$1"
  write_preflight_failure "${reason}"
  echo "${reason}"
  exit 2
}

if ! grep -q 'window_requirement_met' projects/05_alarm_system/scripts/service/run_alarm_service.py; then
  fail_preflight "Project5 service is stale: sync current source before Jetson P4"
fi
if ! grep -q 'requested_window_sec' benchmark/schemas/alarm_system_stability_schema.json; then
  fail_preflight "Project5 stability schema is stale: sync current source before Jetson P4"
fi

RUNNER="projects/05_alarm_system/runners/detector/jetson_yolo11n_detector_service"
MODEL="models/yolo11n/tensorrt/yolo11n_640_jetson_trt_int8_ptq_calib500_minmax_b8.engine"
PLAYLIST="data/videos/runtime_playlist_v1.txt"
for path in "${RUNNER}" "${MODEL}" "${PLAYLIST}"; do
  if [[ ! -e "${path}" ]]; then
    fail_preflight "Required path is missing: ${path}"
  fi
done
if [[ ! -x "${RUNNER}" ]]; then
  fail_preflight "Detector runner is not executable: ${RUNNER}"
fi
if ! command -v tegrastats >/dev/null 2>&1; then
  fail_preflight "tegrastats is required in PATH for Jetson P4"
fi

DETECTOR_OUT="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.jsonl"
DETECTOR_LOG="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_resident_detector.log"
MONITOR_LOG="logs/monitor/05_alarm_system/${BOARD}/${RUN_ID}_tegrastats.log"
SERVICE_STDOUT="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service_stdout.log"
EVENTS="benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl"
ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl"
BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl"
STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"

mkdir -p \
  "$(dirname "${EVENTS}")" \
  "$(dirname "${ALARMS}")" \
  benchmark/processed/05_alarm_system \
  "$(dirname "${DETECTOR_LOG}")" \
  "$(dirname "${MONITOR_LOG}")"

write_status() {
  local state="$1"
  local exit_code="$2"
  local temp_file="${STATUS_FILE}.tmp"
  {
    echo "state=${state}"
    echo "run_id=${RUN_ID}"
    echo "pid=$$"
    echo "exit_code=${exit_code}"
    echo "updated_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "service_stdout=${SERVICE_STDOUT}"
    echo "detector_log=${DETECTOR_LOG}"
    echo "monitor_log=${MONITOR_LOG}"
    echo "stability=${STABILITY}"
  } > "${temp_file}"
  mv "${temp_file}" "${STATUS_FILE}"
}

MONITOR_PID=""
stop_monitor() {
  if [[ -n "${MONITOR_PID}" ]] && kill -0 "${MONITOR_PID}" 2>/dev/null; then
    kill "${MONITOR_PID}" 2>/dev/null || true
    wait "${MONITOR_PID}" 2>/dev/null || true
  fi
  MONITOR_PID=""
}

finish() {
  local exit_code=$?
  stop_monitor
  if [[ "${exit_code}" -eq 0 ]]; then
    write_status "completed" "${exit_code}"
  else
    write_status "failed" "${exit_code}"
  fi
  trap - EXIT
  exit "${exit_code}"
}

trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
write_status "running" "0"

DETECTOR_CMD="${RUNNER} \
  --config projects/05_alarm_system/configs/detector/pipeline/jetson_tensorrt_pipeline.yaml \
  --model-config projects/05_alarm_system/configs/detector/models/yolo11n.yaml \
  --backend-config projects/05_alarm_system/configs/detector/boards/jetson_8gb.yaml \
  --stream-config projects/05_alarm_system/configs/inputs/video_sources.yaml \
  --input-source-id video_set_runtime_v1 \
  --input-source-type video_playlist \
  --input ${PLAYLIST} \
  --duration-sec ${DURATION_SEC} \
  --raw-output ${DETECTOR_OUT} \
  --runtime-log ${DETECTOR_LOG} \
  --preview-window off \
  --inference-workers 1 \
  --queue-capacity 8 \
  --queue-push-timeout-ms 20"

tegrastats --interval 1000 --logfile "${MONITOR_LOG}" &
MONITOR_PID=$!

echo "detector_startup_timeout_sec=${DETECTOR_STARTUP_TIMEOUT_SEC}"
echo "detector_poll_interval_sec=${DETECTOR_POLL_INTERVAL_SEC}"

P4_START_EPOCH=$(date +%s)
python3 projects/05_alarm_system/scripts/service/run_alarm_service.py \
  --run-id "${RUN_ID}" \
  --board "${BOARD}" \
  --board-name "Jetson Xavier NX 8GB" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --detector-mode resident_process \
  --detector-command "${DETECTOR_CMD}" \
  --detector-output "${DETECTOR_OUT}" \
  --detector-runtime-log "${DETECTOR_LOG}" \
  --detector-startup-timeout-sec "${DETECTOR_STARTUP_TIMEOUT_SEC}" \
  --detector-poll-interval-sec "${DETECTOR_POLL_INTERVAL_SEC}" \
  --rules projects/05_alarm_system/configs/event_rules/jetson_rules.yaml \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --queue-capacity 12 \
  --stability-tier smoke \
  --window-sec "${DURATION_SEC}" \
  --status not_verified \
  --service-status stopped \
  --monitor-log "${MONITOR_LOG}" \
  --text-mode template \
  --text-max-calls 0 \
  --vlm-mode stub \
  --vlm-max-calls 0 \
  2>&1 | tee "${SERVICE_STDOUT}"
SERVICE_EXIT=${PIPESTATUS[0]}
P4_END_EPOCH=$(date +%s)
P4_ELAPSED_SEC=$((P4_END_EPOCH - P4_START_EPOCH))
stop_monitor

echo "SERVICE_EXIT=${SERVICE_EXIT}"
echo "P4_ELAPSED_SEC=${P4_ELAPSED_SEC}"
if [[ "${SERVICE_EXIT}" -ne 0 ]]; then
  echo "P4 failed: service returned ${SERVICE_EXIT}. See ${SERVICE_STDOUT} and ${DETECTOR_LOG}"
  exit "${SERVICE_EXIT}"
fi
if [[ "${P4_ELAPSED_SEC}" -lt "${DURATION_SEC}" ]]; then
  echo "P4 failed: wall-clock duration is shorter than ${DURATION_SEC} seconds"
  exit 1
fi
if [[ ! -s "${MONITOR_LOG}" ]]; then
  echo "P4 failed: monitor log is missing or empty"
  exit 1
fi

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${EVENTS}" \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_event_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${ALARMS}" \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_alarm_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${BENCHMARK}" \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_raw_schema_check.md" || exit $?
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "${STABILITY}" \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_resident_stability_schema_check.md" || exit $?

python3 - "${STABILITY}" "${DURATION_SEC}" <<'PY'
import json
import sys

path, expected = sys.argv[1], float(sys.argv[2])
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
if row.get("requested_window_sec") != expected:
    raise SystemExit("P4 failed: requested_window_sec mismatch")
if row.get("window_sec", 0) < expected or row.get("window_requirement_met") is not True:
    raise SystemExit("P4 failed: stability raw does not prove the requested wall-clock duration")
if row.get("llm_call_count") != 0 or row.get("vlm_call_count") != 0:
    raise SystemExit("P4 failed: template/stub run unexpectedly invoked a real model")
PY

echo "P4_RESULT=resident_detector_smoke_pass_with_template_stub_workers"
echo "detector_log=${DETECTOR_LOG}"
echo "monitor_log=${MONITOR_LOG}"
echo "stability=${STABILITY}"
