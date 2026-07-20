#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-}"
BOARD="${BOARD:-jetson_8gb}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
DURATION_SEC="${DURATION_SEC:-7200}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-2}"
ASYNC_LAUNCH_MODE="${ASYNC_LAUNCH_MODE:-postrun}"
ASYNC_VLM_MAX_CALLS="${ASYNC_VLM_MAX_CALLS:-2}"
ASYNC_VLM_REQUIRE_PASS_ROWS="${ASYNC_VLM_REQUIRE_PASS_ROWS:-2}"
ASYNC_POSTRUN_COOLDOWN_SEC="${ASYNC_POSTRUN_COOLDOWN_SEC:-30}"
VLM_RETRY_BACKOFF_SEC="${VLM_RETRY_BACKOFF_SEC:-30}"
VLM_ONCE_PREWARM_REQUEST="${VLM_ONCE_PREWARM_REQUEST:-1}"
VLM_ONCE_PREWARM_MAX_TOKENS="${VLM_ONCE_PREWARM_MAX_TOKENS:-8}"

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required, for example: export RUN_ID=20260716_jetson_8gb_alarm_service_route_b_target_v1"
  exit 2
fi
if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi
if [[ "${ASYNC_LAUNCH_MODE}" != "postrun" ]]; then
  echo "ASYNC_LAUNCH_MODE must stay postrun for the accepted Jetson target route, got: ${ASYNC_LAUNCH_MODE}"
  exit 2
fi

echo "jetson_route_b_target_mode=realtime_detector_text_plus_postrun_async_vlm"
echo "detector_duration_sec=${DURATION_SEC}"
echo "text_max_calls=${TEXT_MAX_CALLS}"
echo "async_launch_mode=${ASYNC_LAUNCH_MODE}"
echo "async_vlm_max_calls=${ASYNC_VLM_MAX_CALLS}"
echo "async_vlm_require_pass_rows=${ASYNC_VLM_REQUIRE_PASS_ROWS}"
echo "async_postrun_cooldown_sec=${ASYNC_POSTRUN_COOLDOWN_SEC}"
echo "vlm_retry_backoff_sec=${VLM_RETRY_BACKOFF_SEC}"
echo "vlm_once_prewarm_request=${VLM_ONCE_PREWARM_REQUEST}"
echo "vlm_once_prewarm_max_tokens=${VLM_ONCE_PREWARM_MAX_TOKENS}"

export STABILITY_TIER=target
export SERVICE_MODE_KEY="resident_service_target_mode"
export SERVICE_MODE_VALUE="resident_detector_plus_resident_text_vlm_stub"
export RUN_LABEL="P9 route-B realtime target"
export RESULT_VAR_NAME="JETSON_P9_ROUTE_B_REALTIME_RESULT"
export RESULT_TAG="detector_text_resident_vlm_stub_target_pass"
export DURATION_SEC
export TEXT_MAX_CALLS
export ASYNC_LAUNCH_MODE
export ASYNC_VLM_MAX_CALLS
export ASYNC_VLM_REQUIRE_PASS_ROWS
export ASYNC_POSTRUN_COOLDOWN_SEC
export VLM_RETRY_BACKOFF_SEC
export VLM_ONCE_PREWARM_REQUEST
export VLM_ONCE_PREWARM_MAX_TOKENS

bash projects/05_alarm_system/scripts/service/run_jetson_p7_route_b_dual_service_smoke.sh

STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"
ASYNC_VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_outputs.jsonl"
ASYNC_ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarm_enriched.jsonl"
ASYNC_BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_enriched_benchmark.jsonl"

python3 - "${STABILITY}" "${DURATION_SEC}" <<'PY'
import json
import sys

path = sys.argv[1]
expected_window = float(sys.argv[2])
with open(path, encoding="utf-8") as handle:
    row = json.loads(handle.readline())
for key in (
    "stability_tier",
    "window_sec",
    "requested_window_sec",
    "window_requirement_met",
    "detection_fps",
    "event_count",
    "alarm_count",
    "llm_call_count",
    "vlm_call_count",
    "drop_count",
    "status",
    "service_status",
):
    print(f"{key}={row.get(key)}")
if row.get("stability_tier") != "target":
    raise SystemExit("P9 route-B target failed: stability_tier != target")
if row.get("requested_window_sec") != expected_window:
    raise SystemExit("P9 route-B target failed: requested_window_sec mismatch")
if row.get("window_requirement_met") is not True:
    raise SystemExit("P9 route-B target failed: requested wall-clock duration was not met")
if row.get("drop_count") != 0:
    raise SystemExit("P9 route-B target failed: drop_count must stay at 0")
PY

echo "JETSON_P9_ROUTE_B_TARGET_RESULT=realtime_detector_text_plus_postrun_async_vlm_target_ready"
echo "stability=${STABILITY}"
echo "async_vlm=${ASYNC_VLM}"
echo "async_alarm_enriched=${ASYNC_ALARMS}"
echo "async_benchmark_enriched=${ASYNC_BENCHMARK}"
