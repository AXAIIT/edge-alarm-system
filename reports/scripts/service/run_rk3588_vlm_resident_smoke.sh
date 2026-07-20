#!/usr/bin/env bash
set -euo pipefail

BOARD="${BOARD:-rk3588_8gb}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d)_rk3588_8gb_alarm_service_resident_vlm_smoke_v1}"
ENV_BASELINE_ID="${ENV_BASELINE_ID:-20260611_rk3588_8gb_env_baseline}"
EVENTS_INPUT="${EVENTS_INPUT:-benchmark/raw/05_alarm_system/${BOARD}/events/20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1_events_with_assets.jsonl}"
MODEL_CONFIG="${MODEL_CONFIG:-projects/05_alarm_system/configs/models/rk3588_model_combo.yaml}"
VLM_RUNNER="${VLM_RUNNER:-projects/05_alarm_system/runners/rkllm_resident_vlm_server/build/rkllm_resident_vlm_server}"
VISION_MODEL="${VISION_MODEL:-models/llm_vlm/Qwen3-VL-2B-RKNN/qwen3-vl_vision_384_patch_embed_cpu_rk3588.rknn}"
DECODER_MODEL="${DECODER_MODEL:-models/llm_vlm/Qwen3-VL-2B-RKLLM/qwen3-vl-2b-instruct_w8a8_rk3588.rkllm}"
MAX_EVENTS="${MAX_EVENTS:-3}"
TEXT_MAX_CALLS="${TEXT_MAX_CALLS:-0}"
VLM_MAX_CALLS="${VLM_MAX_CALLS:-3}"
VLM_CTX="${VLM_CTX:-2048}"
VLM_MAX_TOKENS="${VLM_MAX_TOKENS:-256}"
VLM_TIMEOUT_MS="${VLM_TIMEOUT_MS:-70000}"
VLM_STARTUP_TIMEOUT_MS="${VLM_STARTUP_TIMEOUT_MS:-30000}"

export BOARD RUN_ID

mkdir -p \
  "benchmark/raw/05_alarm_system/${BOARD}/events" \
  "benchmark/raw/05_alarm_system/${BOARD}/alarms" \
  "benchmark/processed/05_alarm_system" \
  "logs/runtime/05_alarm_system/${BOARD}" \
  "logs/benchmark/05_alarm_system/${BOARD}"

test -s "${EVENTS_INPUT}"
test -s "${MODEL_CONFIG}"
test -x "${VLM_RUNNER}"
test -s "${VISION_MODEL}"
test -s "${DECODER_MODEL}"

python3 projects/05_alarm_system/scripts/service/run_alarm_service.py \
  --run-id "${RUN_ID}" \
  --board "${BOARD}" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --detector-mode events_input \
  --events-input "${EVENTS_INPUT}" \
  --model-config "${MODEL_CONFIG}" \
  --text-mode template \
  --text-max-calls "${TEXT_MAX_CALLS}" \
  --vlm-mode rkllm_multimodal_resident \
  --rkllm-mm-resident-runner "${VLM_RUNNER}" \
  --vision-model "${VISION_MODEL}" \
  --decoder-model "${DECODER_MODEL}" \
  --vlm-ctx "${VLM_CTX}" \
  --vlm-max-tokens "${VLM_MAX_TOKENS}" \
  --vlm-timeout-ms "${VLM_TIMEOUT_MS}" \
  --vlm-startup-timeout-ms "${VLM_STARTUP_TIMEOUT_MS}" \
  --vlm-max-calls "${VLM_MAX_CALLS}" \
  --max-events "${MAX_EVENTS}" \
  --status not_verified \
  --service-status stopped

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl" \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_event_package_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl" \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_alarm_json_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl" \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output "benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_raw_schema_check.md"

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input "benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl" \
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
pids = sorted({row.get("resident_server_pid") for row in rows if row.get("resident_server_pid") is not None})
loads = sorted({row.get("resident_model_load_count") for row in rows if row.get("resident_model_load_count") is not None})
request_indexes = [row.get("resident_request_index") for row in rows if row.get("resident_request_index") is not None]
print(f"vlm_rows={len(rows)}")
print(f"vlm_bad_rows={len(bad)}")
print(f"resident_server_pids={pids}")
print(f"resident_model_load_counts={loads}")
print(f"resident_request_indexes={request_indexes}")
if bad:
    print("bad_event_ids=", [row.get("event_id") for row in bad[:5]])
    sys.exit(1)
if len(pids) != 1 or loads != [1]:
    sys.exit(1)
PY

echo "RESIDENT_VLM_SMOKE_RESULT=resident_vlm_worker_smoke_pass"
