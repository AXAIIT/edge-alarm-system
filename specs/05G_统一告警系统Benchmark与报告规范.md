# 05G_统一告警系统Benchmark与报告规范

## 执行原则

本规范用于统一项目五的 raw result、event package、告警 JSON、稳定性 raw、模型组合矩阵、端到端 benchmark、稳定性报告和失败降级报告。

项目五正式主线只覆盖 Jetson 8GB 和 RK3588 8GB。RDK X5 因项目四准入失败从项目五实验、横向 benchmark 和稳定性验收中移除。

项目五允许不同板卡使用不同 detector runtime、LLM/VLM runtime、服务框架和队列实现，但统一报告必须保证：

- 每个系统能力结论都来自 selected run。
- 每个 selected run 都通过 schema 校验或明确标记降级原因。
- mock/stub 只能进入接口联调表，不能进入正式系统能力结论。
- single-shot LLM/VLM 只能进入模型 smoke 表，不能进入 resident service 结论。
- post-detector chain pass 只能说明检测后处理闭环，不能自动声明完整在线常驻服务。
- 直接调用项目三/项目四脚本只能进入 artifact replay 或 legacy smoke 表，不能进入独立 Project5 runtime 结论。
- LLM/VLM 输出不能覆盖 event package 中的检测事实。
- 缺失、失败、fallback、not_verified、blocked、not_executed 都必须显式进入报告。

## 适用范围

本规范覆盖：

- `projects/05_alarm_system/reports/board_matrix.md`
- `projects/05_alarm_system/reports/input_sources.md`
- `projects/05_alarm_system/reports/yolo11n_realtime_benchmark.md`
- `projects/05_alarm_system/reports/llm_vlm_benchmark.md`
- `projects/05_alarm_system/reports/video_understanding_benchmark.md`
- `projects/05_alarm_system/reports/event_pipeline.md`
- `projects/05_alarm_system/reports/alarm_system_benchmark.md`
- `projects/05_alarm_system/reports/stability_report.md`
- `projects/05_alarm_system/reports/failure_and_fallback.md`
- `projects/05_alarm_system/reports/troubleshooting.md`
- `benchmark/raw/05_alarm_system/**/*.jsonl`
- `benchmark/schemas/alarm_system_raw_schema.json`
- `benchmark/schemas/alarm_system_stability_schema.json`
- `benchmark/schemas/alarm_event_package_schema.json`
- `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json`
- `projects/05_alarm_system/specs/05H_告警业务语义与事件规则规范.md`
- `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`
- `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md`
- `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md`

## 前置条件

统一汇总前必须具备：

- 项目五环境基线，格式对齐 `projects/05_alarm_system/specs/00_environment_baseline_template.md`。
- run 记录，格式对齐 `projects/05_alarm_system/specs/00_run_record_template.md`。
- 输入源 manifest：`projects/05_alarm_system/configs/inputs/video_sources.yaml`。
- 模型组合配置，并符合 `projects/05_alarm_system/configs/models/model_combo_schema.yaml`。
- event package、告警 JSON、per-event raw 和稳定性 raw 的 schema。
- 项目一、三、四的继承证据。
- 项目五独立代码边界检查结果，至少包含 `code_boundary_status`。

缺少任一前置证据时仍可生成报告，但必须标记 `missing`、`not_verified`、`blocked` 或 `not_executed`，不能留空。

`target=pc` 只能用于脚本调试、CPU baseline、接口联调或模型格式预检。PC run 可以进入数据质量检查、问题库或接口联调表，但不能作为 Jetson 或 RK3588 的系统能力结论，也不能被选为双板正式 selected run。

## 1. Schema 校验

### 1.1 per-event 告警 raw

当前仓库可执行的最小校验器是 `projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py`，按单个 JSONL 输入校验 required 字段。下面命令用于当前阶段；若后续实现递归 report validator，必须保持同等或更严格的检查。

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/<board>/<run_id>_alarm_system_benchmark.jsonl \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output benchmark/processed/05_alarm_system/<run_id>_alarm_system_raw_schema_check.md
```

校验重点：

- `measurement_granularity = per_event`。
- 一行必须表示一个 `event_id` 对应的一次告警生成记录。
- 必须包含 `schema_version`、`target`、`environment_baseline_id`、`model_combo_id`、`fallback_status`、`raw_event_path`、`alarm_json_path`、日志路径。
- `p50/p90/p95/p99`、平均 FPS、schema pass rate、总事件数不能写入 per-event raw 行，必须由 processed result 聚合。

### 1.2 event package

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/<board>/events/<run_id>_events.jsonl \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output benchmark/processed/05_alarm_system/<run_id>_event_package_schema_check.md
```

校验重点：

- `event_id` 在同一 run 内唯一。
- `alarm_domain`、`alarm_type`、`event_stage`、`trigger_rule_id` 必须符合 05H；正式 run 不能使用 `generic_object_event`。
- `detections` 必须保留检测事实。
- ROI 坐标必须使用源图坐标系，记录 padding 和 resize。
- `queue_metrics.drop_policy` 必须是固定枚举。

### 1.3 告警 JSON

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/<board>/alarms/<run_id>_alarms.jsonl \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output benchmark/processed/05_alarm_system/<run_id>_alarm_schema_check.md
```

校验重点：

- `detections[].source` 必须为 `event_package`。
- `fallback_status` 必须字段化。
- `risk_level` 和 `recommended_action` 必须使用枚举。
- `json_fact_conflict=true` 时必须进入问题库。

### 1.4 稳定性 raw

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/<board>/stability/<run_id>_stability.jsonl \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output benchmark/processed/05_alarm_system/<run_id>_stability_schema_check.md
```

校验重点：

- `measurement_granularity = time_window`。
- 一行必须表示一个稳定性时间窗口采样。
- 30 分钟 required 未完成时不能写成 pass。

`validate_alarm_jsonl.py` 只证明字段级 schema 通过，不能替代 event trace、事实冲突、固定输入对齐、任务级告警质量或稳定性持续时长判断。

## 2. 最新有效 run 选择

同一组合可能有多次 run，统一报告必须先选择最新有效 run。分组维度：

```text
board
target
alarm_domain
alarm_type
input_source_id
model_combo_id
event_rules_sha256
detector_backend
llm_model
vlm_model
video_model
pipeline_mode
stability_tier
```

状态处理规则：

| status | 汇总处理 |
|---|---|
| `pass` | 可进入正式矩阵 |
| `degraded` | 可进入矩阵，但必须显著标注降级原因 |
| `not_verified` | 只能进入状态表，不能作为性能或系统能力结论 |
| `fail` | 不进入正式性能结论，必须进入问题库 |
| `blocked` | 不进入正式性能结论，只进入状态表 |
| `not_executed` | 只进入状态表 |
| `mock` | 只能进入接口联调表，不能进入正式系统能力结论 |
| `stub` | 只能进入接口联调表，不能进入正式系统能力结论 |
| `single_shot_model_smoke` | 只能进入模型 smoke 表，不能作为 resident service 结论 |
| `post_detector_chain_pass` | 可以进入链路闭环表，不能作为完整在线服务结论 |
| `resident_service_smoke` | 可以进入服务化 smoke 表，不能替代 required |
| `resident_service_required` | 可作为项目五最低在线系统验收结论 |
| `artifact_replay_pass` | 可以进入后处理链路表，不能作为完整在线服务结论 |
| `legacy_adapter_smoke` | 可以进入模型或接口 smoke 表，不能作为独立 runtime 结论 |
| `independent_runtime_pass` | 可以作为 Project5 独立代码边界通过证据，仍需结合 05K 稳定性 |
| `coupled_runtime_not_accepted` | 不进入正式验收，必须进入问题库 |

选择优先级：

1. `pass` 优先于 `degraded`。
2. schema 校验通过优先。
3. run、环境基线、输入源、模型组合、event package、alarm JSON、raw result、runtime 日志、monitor 日志、固定输入对齐和任务级告警质量评估完整优先。
4. 项目四准入引用完整优先。
5. 日期最新优先。
6. 仍然并列时按 `run_id` 字典序选择。

被排除 run 必须写入：

```text
benchmark/processed/05_alarm_system/excluded_runs.md
```

排除清单至少包含：`run_id`、`status`、`excluded_reason`、`missing_evidence`、`schema_check_result`、`related_troubleshooting_id`。

## 3. processed result 输出

统一汇总至少生成：

```text
benchmark/processed/05_alarm_system/schema_check_report.md
benchmark/processed/05_alarm_system/alarm_schema_check_report.md
benchmark/processed/05_alarm_system/event_package_check_report.md
benchmark/processed/05_alarm_system/stability_schema_check_report.md
benchmark/processed/05_alarm_system/board_matrix.csv
benchmark/processed/05_alarm_system/alarm_system_summary.csv
benchmark/processed/05_alarm_system/stability_summary.csv
benchmark/processed/05_alarm_system/excluded_runs.md
```

processed 指标来源：

| 指标 | 来源 |
|---|---|
| p50/p90/p95/p99 | per-event raw 或 stability raw 聚合 |
| schema pass rate | alarm JSON 校验结果聚合 |
| event trace pass rate | event package 与告警 JSON 追溯校验聚合 |
| fact conflict rate | `json_fact_conflict` 和事实冲突检查聚合 |
| fixed_input_alignment_status / task_level_quality_status | 固定事件对齐和固定事件集任务质量评估 |
| code_boundary_status | 05L 独立代码边界检查结果 |
| event_count / alarm_count | per-event raw 或 stability raw 聚合 |
| average FPS | stability raw 时间窗口聚合 |
| fallback_count | per-event raw 或 stability raw 聚合 |
| event_count_by_alarm_domain / event_count_by_alarm_type | event package、per-event raw 或 stability raw 聚合 |
| fallback_count_by_domain | per-event raw 的 `fallback_status` 和 `alarm_domain` 聚合 |
| board matrix | selected run 和模型组合配置聚合 |

## 4. 报告生成

报告更新顺序：

1. `input_sources.md`
2. `board_matrix.md`
3. `event_pipeline.md`
4. `yolo11n_realtime_benchmark.md`
5. `llm_vlm_benchmark.md`
6. `video_understanding_benchmark.md`
7. `alarm_system_benchmark.md`
8. `stability_report.md`
9. `failure_and_fallback.md`
10. `troubleshooting.md`

每个报告必须说明：

- 当前状态：`not_executed`、`not_verified`、`blocked`、`degraded`、`pass` 或 `fail`。
- selected run。
- raw result。
- event package。
- alarm JSON。
- 固定输入对齐状态。
- 任务级告警质量状态。
- 质量对齐豁免原因，如果适用。
- runtime log。
- monitor log。
- 项目四准入引用。
- 代码边界状态：`independent_runtime_pass`、`artifact_replay_pass`、`legacy_adapter_smoke` 或 `coupled_runtime_not_accepted`。
- 缺失证据和 excluded runs。

## 5. MLPerf-style Summary

`alarm_system_benchmark.md` 和每块板的系统报告必须包含：

```text
## MLPerf-style Summary

- Task:
- Board:
- Input source:
- Detector:
- Text LLM:
- Image VLM:
- Video model:
- Backend/runtime:
- Dataset/input set:
- Scenario:
- Quality target:
- Change type:
- Fixed-input alignment:
- Task-level quality:
- Quality alignment exemption:
- Performance result:
- Resource result:
- Stability result:
- Raw result:
- Event package:
- Alarm JSON:
- Logs:
- Repro command:
- Known limitations:
- Code boundary:
```

字段不可观测时写 `not_observable: reason`，不能删除字段。

## 6. 验收标准

本规范完成时必须满足：

- 项目五所有正式 raw result 可以被统一 schema 校验。
- event package、alarm JSON、per-event raw 和 stability raw 的粒度分离清楚。
- 每块板都有 selected run 或明确的 blocked/not_executed 原因。
- mock/stub 不会进入正式系统能力结论。
- legacy adapter 和 artifact replay 不会被写成完整在线常驻系统结论。
- `board_matrix.md` 能直接说明 Jetson/RK3588 模型组合、准入等级、运行后端和证据路径。
- `alarm_system_benchmark.md` 能追溯到 event package、alarm JSON、raw result、日志和项目四准入。
- 模型组合、prompt、事件规则、ROI、fallback 或告警 schema 变化后的质量结论必须同时包含固定输入对齐和任务级告警质量评估；缺任一层时不能写 `pass`。
- `stability_report.md` 至少区分 smoke、required、target、stress，并说明未完成状态。
- 所有失败、fallback、事实冲突和证据缺失都进入问题库或失败降级报告。
