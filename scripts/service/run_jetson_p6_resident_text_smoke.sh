#!/usr/bin/env bash
set -euo pipefail

BOARD="${BOARD:-jetson_8gb}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d)_jetson_8gb_alarm_service_resident_text_smoke_v1}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260609_jetson_8gb_env_baseline}"
EVENTS_INPUT="${EVENTS_INPUT:-benchmark/raw/05_alarm_system/${BOARD}/events/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_events.jsonl}"
MODEL_CONFIG="${MODEL_CONFIG:-projects/05_alarm_system/configs/models/jetson_model_combo.yaml}"
TEXT_MODEL="${TEXT_MODEL:-${QWEN3_GGUF:-}}"
LLAMA_BIN_VALUE="${LLAMA_BIN:-llama-cli}"
LLAMA_SERVER_BIN_VALUE="${LLAMA_SERVER_BIN:-}"
MAX_EVENTS="${MAX_EVENTS:-3}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-3}"
TEXT_CTX="${TEXT_CTX:-2048}"
TEXT_MAX_TOKENS="${TEXT_MAX_TOKENS:-128}"
TEXT_TIMEOUT_MS="${TEXT_TIMEOUT_MS:-120000}"
TEXT_STARTUP_TIMEOUT_MS="${TEXT_STARTUP_TIMEOUT_MS:-90000}"
TEXT_NGL="${TEXT_NGL:-0}"
TEXT_NO_KV_OFFLOAD="${TEXT_NO_KV_OFFLOAD:-1}"
TEXT_DEVICE="${TEXT_DEVICE:-none}"
QWEN_NO_THINK="${QWEN_NO_THINK:-1}"

export BOARD RUN_ID

if [[ "${BOARD}" != "jetson_8gb" ]]; then
  echo "BOARD must be jetson_8gb, got: ${BOARD}"
  exit 2
fi
if [[ -z "${TEXT_MODEL}" ]]; then
  echo "TEXT_MODEL or QWEN3_GGUF is required"
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

test -s "${EVENTS_INPUT}"
test -s "${MODEL_CONFIG}"
test -s "${TEXT_MODEL}"

LLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl"
VLM="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl"
ALARMS="benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl"
BENCHMARK="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl"
STABILITY="benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl"
TEXT_RUNTIME_DIR="logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_cpp_runtime"

rm -f "${LLM}" "${VLM}" "${ALARMS}" "${BENCHMARK}" "${STABILITY}"
rm -rf "${TEXT_RUNTIME_DIR}"
mkdir -p "${TEXT_RUNTIME_DIR}"

echo "text_ngl=${TEXT_NGL}"
echo "text_no_kv_offload=${TEXT_NO_KV_OFFLOAD}"
echo "text_device=${TEXT_DEVICE}"
echo "qwen_no_think=${QWEN_NO_THINK}"

ARGS=(
  python3 projects/05_alarm_system/scripts/service/run_alarm_service.py
  --run-id "${RUN_ID}"
  --board "${BOARD}"
  --environment-baseline-id "${ENV_BASELINE_ID}"
  --detector-mode events_input
  --events-input "${EVENTS_INPUT}"
  --model-config "${MODEL_CONFIG}"
  --text-mode llama_cpp_resident
  --text-model-path "${TEXT_MODEL}"
  --llama-bin "${LLAMA_BIN_VALUE}"
  --ngl "${TEXT_NGL}"
  --text-ctx "${TEXT_CTX}"
  --text-max-tokens "${TEXT_MAX_TOKENS}"
  --text-timeout-ms "${TEXT_TIMEOUT_MS}"
  --text-startup-timeout-ms "${TEXT_STARTUP_TIMEOUT_MS}"
  --text-runtime-log-dir "${TEXT_RUNTIME_DIR}"
  --text-max-calls "${TEXT_MAX_CALLS}"
  --text-device "${TEXT_DEVICE}"
  --vlm-mode stub
  --vlm-max-calls 0
  --max-events "${MAX_EVENTS}"
  --status not_verified
  --service-status stopped
)

if [[ -n "${LLAMA_SERVER_BIN_VALUE}" ]]; then
  ARGS+=(--llama-server-bin "${LLAMA_SERVER_BIN_VALUE}")
fi
if [[ "${TEXT_NO_KV_OFFLOAD}" == "1" ]]; then
  ARGS+=(--text-no-kv-offload)
fi
if [[ "${QWEN_NO_THINK}" == "1" ]]; then
  ARGS+=(--qwen-no-think)
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
llm_path = Path(f"benchmark/raw/05_alarm_system/{board}/{run_id}_llm_outputs.jsonl")
rows = [json.loads(line) for line in llm_path.read_text(encoding="utf-8").splitlines() if line.strip()]
bad = [row for row in rows if row.get("status") != "pass" or not row.get("llm_explanation")]
pass_rows = [row for row in rows if row.get("status") == "pass"]
pids = sorted({row.get("resident_server_pid") for row in pass_rows if row.get("resident_server_pid") is not None})
loads = sorted({row.get("resident_model_load_count") for row in pass_rows if row.get("resident_model_load_count") is not None})
indexes = [row.get("resident_request_index") for row in pass_rows if row.get("resident_request_index") is not None]
print(f"llm_rows={len(rows)}")
print(f"llm_bad_rows={len(bad)}")
print(f"resident_server_pids={pids}")
print(f"resident_model_load_counts={loads}")
print(f"resident_request_indexes={indexes}")
if bad:
    print("bad_event_ids=", [row.get("event_id") for row in bad[:5]])
    sys.exit(1)
if len(pids) != 1 or loads != [1]:
    raise SystemExit("Jetson resident text smoke failed: resident pid/load_count mismatch")
if indexes != sorted(indexes):
    raise SystemExit("Jetson resident text smoke failed: request indexes are not monotonic")
PY

python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

board = os.environ["BOARD"]
run_id = os.environ["RUN_ID"]
alarm_path = Path(f"benchmark/raw/05_alarm_system/{board}/alarms/{run_id}_alarms.jsonl")
alarms = [json.loads(line) for line in alarm_path.read_text(encoding="utf-8").splitlines() if line.strip()]
guarded = [alarm for alarm in alarms if alarm.get("json_fact_conflict")]
invalid = [
    alarm for alarm in guarded
    if alarm.get("fallback_status", {}).get("alarm_json") != "fact_conflict_detected"
    or not alarm.get("fact_conflict_detail")
]
print(f"fact_guard_alarm_rows={len(alarms)}")
print(f"fact_guard_replaced_rows={len(guarded)}")
print(f"fact_guard_invalid_rows={len(invalid)}")
if invalid:
    print("fact_guard_invalid_event_ids=", [alarm.get("event_id") for alarm in invalid[:5]])
    sys.exit(1)
PY

echo "JETSON_P6_RESULT=resident_text_worker_smoke_pass"
