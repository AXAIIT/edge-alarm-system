# 项目五 run 记录模板

本模板用于项目五每一次模型组合冻结、检测接入、事件触发、ROI/短片段生成、LLM/VLM 调用、告警 JSON、端到端 benchmark、稳定性和异常注入 run。执行者可以增加字段，但不能删除下面的硬性字段。

项目五统一使用目录式 run：

```text
projects/05_alarm_system/runs/<run_id>/run.md
```

每个 run 可以附带：

```text
projects/05_alarm_system/runs/<run_id>/outputs/
projects/05_alarm_system/runs/<run_id>/config_snapshot/
projects/05_alarm_system/runs/<run_id>/event_samples/
projects/05_alarm_system/runs/<run_id>/alarm_samples/
projects/05_alarm_system/runs/<run_id>/notes.md
```

状态枚举：

| status | 含义 | 是否可进入正式矩阵 | 要求 |
|---|---|---|---|
| `pass` | 证据完整且达到本 spec 验收条件 | 是 | 必须有 raw、event package、alarm JSON、log、monitor |
| `degraded` | 链路可用但存在降级、性能、资源或证据限制 | 可进入矩阵但必须显著标注 | 必须说明降级原因 |
| `fail` | 链路、schema、资源、稳定性或质量失败 | 否 | 必须进入问题库 |
| `blocked` | 缺硬件、模型、前置项目证据、权限或外部条件 | 否 | 必须说明恢复条件 |
| `not_executed` | 尚未执行且不是失败 | 否 | 必须说明未执行原因 |
| `not_verified` | 有结果但缺关键证据，不能支撑结论 | 否 | 补齐证据后重新生成 run |
| `mock` | mock 数据或 mock 模型联调 | 只能进入接口联调表 | 不能作为系统能力结论 |
| `stub` | stub 模块联调 | 只能进入接口联调表 | 不能作为系统能力结论 |
| `single_shot_model_smoke` | 真实 LLM/VLM 单次调用可用 | 只能进入模型 smoke 表 | 不能作为 resident service |
| `post_detector_chain_pass` | 项目三 detector raw 加项目五后处理闭环 | 可进入链路闭环表 | 不能作为完整在线服务 |
| `resident_service_required` | 30 分钟常驻服务最低验收通过 | 是 | 还必须满足 05L 独立代码边界 |
| `artifact_replay_pass` | 读取前序 raw/artifact 完成项目五链路 | 只能进入 replay 表 | 不能作为独立 runtime |
| `legacy_adapter_smoke` | 直接调用前序项目脚本或 wrapper 的 smoke | 只能进入 smoke 表 | 不能作为独立 runtime |
| `independent_runtime_pass` | Project5 服务入口和 worker 均在项目五本地实现 | 可作为代码边界证据 | 仍需结合 05K 稳定性 |
| `coupled_runtime_not_accepted` | 最终服务仍耦合项目三/四脚本 | 否 | 必须进入问题库 |

```yaml
run_id:
date:
spec_ref:
stage:
status:
status_reason:

environment:
  environment_baseline_id:
  board:
  target:
  os:
  runtime_versions:
  power_mode:
  cooling:
  swap_policy:

upstream_refs:
  project1_vision_deploy:
    model_artifact_path:
    model_artifact_sha256:
    benchmark_report:
  project3_video_pipeline:
    selected_run_id:
    runtime_benchmark:
    stability_report:
  project4_llm_vlm:
    selected_decision_report:
    selected_model_runs:
    project5_admission_levels:

model_combo:
  model_combo_id:
  detector_model:
  detector_backend:
  detector_artifact_sha256:
  detector_precision:
  text_llm:
  image_vlm:
  video_vlm:
  project4_decision_refs:

model_execution:
  detector_execution: real_project3_pipeline | adapter_replay | mock | not_executed
  llm_execution: llama_cpp_qwen3 | rkllm_qwen3 | template | mock | not_executed
  vlm_execution: qwen3_vl_real_model | route_stub_only | mock | not_executed
  video_execution: disabled_by_project4_decision | real_model | mock | not_executed
  resident_detector:
  resident_llm:
  resident_vlm:
  code_boundary_status: independent_runtime_pass | artifact_replay_pass | legacy_adapter_smoke | coupled_runtime_not_accepted | not_checked
  execution_evidence:
    detector_raw:
    llm_raw:
    vlm_raw:
    video_raw:
    runtime_logs:
    monitor_logs:
  evidence_boundary:
    project4_admission_only:
    project5_real_execution:
    template_or_stub:

input_source:
  input_source_id:
  source_type:
  uri:
  video_sha256:
  camera_id:
  fps:
  resolution:
  duration_sec:

event_config:
  alarm_task_scope:
  alarm_domains:
  alarm_types:
  event_rules_path:
  event_rules_sha256:
  queue_policy:
  queue_capacity:
  cooldown_seconds:
  trigger_thresholds:

service:
  service_name:
  service_manager:
  project5_service_entrypoint:
  uses_project3_runtime_script:
  uses_project4_runtime_script:
  service_start_status:
  healthcheck_status:
  restart_count:
  journal_log_path:
  container_id:

commands:
  - name:
    command:
    cwd:
    log_path:
    exit_code:

outputs:
  event_package_path:
  alarm_json_path:
  raw_result_path:
  processed_result_path:
  runtime_log_path:
  benchmark_log_path:
  monitor_log_path:
  failure_log_path:
  output_samples_dir:

performance:
  measurement_scope: pipeline | detector_only | event_only | alarm_only | stability
  detection_fps:
  detection_latency_p95_ms:
  event_trigger_latency_ms:
  roi_crop_latency_ms:
  vlm_total_ms:
  video_understanding_total_ms:
  llm_total_ms:
  end_to_end_alarm_ms:
  json_schema_pass_rate:

resource:
  memory_peak_mb:
  swap_used_mb:
  temperature_max_c:
  power_w:
  power_mode:
  cpu_gpu_npu_utilization:

stability:
  stability_tier: smoke | required | target | stress | not_applicable
  target_duration_sec:
  actual_duration_sec:
  event_count:
  alarm_count:
  fallback_count:
  error_count:
  restart_count:
  reconnect_count:
  crash_count:

issues:
  related_troubleshooting_id:
  notes:
```

## 记录要求

- run 记录必须引用环境基线、前置项目证据、输入源 manifest、模型组合配置、事件规则、命令、raw result、event package、alarm JSON、runtime 日志、monitor 日志和问题记录。
- `model_execution` 必须明确真实模型、template、mock、stub 和禁用状态。项目四准入结论只能填写 `project4_admission_only`，不能替代项目五真实模型执行证据。
- `code_boundary_status` 必须按 05L 填写。读取项目三 raw 是 `artifact_replay_pass`；直接调用项目四 wrapper 是 `legacy_adapter_smoke`；最终服务仍依赖项目三/四脚本时必须写 `coupled_runtime_not_accepted`。
- 只有 service entrypoint、queue、LLM/VLM worker 和 AlarmSink 均在项目五目录内，并通过 05K/05L 验收，才能写 `independent_runtime_pass`。
- 告警 raw result 必须符合 `benchmark/schemas/alarm_system_raw_schema.json`。
- 稳定性 raw result 必须符合 `benchmark/schemas/alarm_system_stability_schema.json`。
- event package 必须符合 `benchmark/schemas/alarm_event_package_schema.json`。
- 告警 JSON 必须符合 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json`。
- `fail`、`degraded`、`not_verified`、`mock`、`stub` 必须写明原因；失败和降级必须进入 `projects/05_alarm_system/reports/troubleshooting.md` 或 `failure_and_fallback.md`。
