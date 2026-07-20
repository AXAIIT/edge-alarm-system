# 05E_结构化告警JSON规范

## 适用范围

本规范定义项目五结构化告警 JSON 的字段、schema 校验、质量检查和 fallback 行为。

告警 JSON 是项目五最终系统输出。它必须能同时表达原始检测事实、VLM/视频理解补充、LLM 告警解释、系统资源状态、项目四准入引用和降级状态。每条告警 JSON 必须携带 `alarm_domain`、`alarm_type` 和 `event_stage`，用于区分检测候选事件、视觉证据复核、文本解释、系统/模型故障、JSON 质量和视频降级任务。

## 执行原则

LLM/VLM 输出不能覆盖原始检测事实。检测框、类别、置信度、frame_id、event_id 必须来自 event package；LLM 只能生成解释、风险等级和建议动作。任何事实冲突都必须被标记并进入问题库。

## 路径口径

| 类型 | 路径 |
|---|---|
| alarm schema | `projects/05_alarm_system/configs/alarm_schema/` |
| run 记录 | `projects/05_alarm_system/runs/<run_id>/run.md` |
| 告警 JSON | `benchmark/raw/05_alarm_system/<board>/alarms/` |
| schema 校验结果 | `benchmark/processed/05_alarm_system/` |
| runtime 日志 | `logs/runtime/05_alarm_system/<board>/` |
| failure 日志 | `logs/failures/05_alarm_system/<board>/` |
| 报告 | `projects/05_alarm_system/reports/event_pipeline.md`、`projects/05_alarm_system/reports/failure_and_fallback.md` |

## 前置条件

- 已有 event package。
- 已有文本 LLM 输出，或已配置规则模板 fallback。
- VLM/视频理解输出按项目四准入等级可选。
- 已准备 JSON schema。
- 已定义风险等级和 recommended_action 枚举。
- run 记录必须对齐 `projects/05_alarm_system/specs/00_run_record_template.md`。
- event package 必须符合 `benchmark/schemas/alarm_event_package_schema.json`。
- 告警 JSON 必须符合 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json`。
- schema 校验结果必须进入 `projects/05_alarm_system/specs/05G_统一告警系统Benchmark与报告规范.md` 定义的 processed result。

## 必须字段

```text
event_id
timestamp
board
alarm_domain
alarm_type
event_stage
camera_id
source_frame
detections
roi_paths
video_clip_path
vlm_summary
video_summary
llm_explanation
risk_level
recommended_action
system_metrics
model_versions
project4_decision_refs
fallback_status
evidence
schema_version
```

## 字段定义

| 字段 | 要求 |
|---|---|
| `event_id` | 来自 event package，不能重写 |
| `alarm_domain` | 来自 event package 或解释任务路由，表示 `visual_detection`、`visual_evidence`、`text_explanation`、`system_runtime`、`model_runtime`、`json_quality` 或 `video_fallback` |
| `alarm_type` | 来自 event package 或解释任务路由，表示具体候选告警或解释任务 |
| `event_stage` | `candidate`、`verified`、`rejected` 或 `fallback`；第一阶段检测触发默认 `candidate` |
| `detections` | 保留原始类别、置信度、bbox、frame_id |
| `vlm_summary` | 可为空，但必须说明未执行或 fallback 原因 |
| `video_summary` | 可为空，但必须说明未执行或 fallback 原因 |
| `llm_explanation` | 文本解释，不能删除检测事实 |
| `risk_level` | 建议使用 `info`、`low`、`medium`、`high`、`critical` |
| `recommended_action` | 使用 `observe`、`notify_operator`、`inspect_site`、`stop_equipment`、`escalate`、`template_fallback`、`no_action` |
| `system_metrics` | 写入告警生成时的资源状态 |
| `model_versions` | 记录检测、LLM、VLM、视频模型和 runtime |
| `project4_decision_refs` | 引用项目四准入报告或 run_id |
| `fallback_status` | 记录每个子模块是否正常、超时、禁用或回退 |
| `evidence` | raw result、日志、ROI、视频片段路径 |

## 执行步骤

### 1. 建立 run 记录

新建：

```text
projects/05_alarm_system/runs/<date>_<board>_alarm_json_schema/run.md
```

记录 schema 版本、输入 event package、LLM/VLM 输出路径和告警输出路径。

### 2. 汇总上下文

输入包括：

- event package。
- LLM 文本解释。
- VLM 图像解释。
- video summary。
- system metrics。
- 项目四准入引用。
- fallback 状态。

缺失 VLM 或视频理解输出时，不允许删除字段，必须填入 null 或结构化 fallback 原因。

### 3. 生成告警 JSON

推荐命令：

```bash
python3 projects/05_alarm_system/scripts/run_demo/build_alarm_json.py \
  --events benchmark/raw/05_alarm_system/<board>/events/<date>_<board>_event_packages.jsonl \
  --llm benchmark/raw/05_alarm_system/<board>/<date>_<board>_llm_outputs.jsonl \
  --vlm benchmark/raw/05_alarm_system/<board>/<date>_<board>_vlm_outputs.jsonl \
  --video benchmark/raw/05_alarm_system/<board>/<date>_<board>_video_outputs.jsonl \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output benchmark/raw/05_alarm_system/<board>/alarms/<date>_<board>_alarm_json.jsonl \
  > logs/runtime/05_alarm_system/<board>/<date>_<board>_alarm_json.log 2>&1
```

### 4. Schema 校验

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/<board>/alarms/<date>_<board>_alarm_json.jsonl \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output benchmark/processed/05_alarm_system/<date>_<board>_alarm_schema_check.md
```

当前仓库提供的是最小 JSONL schema 校验器，用于检查 required 字段和基础结构。事实冲突、业务质量、固定输入对齐和任务级告警质量必须按本规范第 5 节另行评估，不能只凭 schema check 写 `pass`。

### 5. 事实冲突检查

必须检查：

- LLM 是否把检测类别改成不存在的类别。
- LLM 是否否认 event package 中存在的检测。
- VLM summary 是否与 ROI 或检测类别明显冲突。
- recommended_action 是否与 risk_level 矛盾。

冲突时设置：

```json
{
  "json_fact_conflict": true,
  "fallback_status": {
    "alarm_json": "fact_conflict_detected"
  }
}
```

Schema 通过只能证明告警 JSON 格式合格，不能单独作为系统质量 `pass`。如果 prompt、schema、事件规则、ROI、fallback 或模型组合发生变化，必须按 `docs/standards/模型变更质量对齐规范.md` 补充固定事件对齐和固定事件集任务级质量评估；缺任务级评估时状态只能写 `not_verified`。

### 6. Fallback 输出

LLM/VLM 失败时，仍必须输出可用告警 JSON。推荐 fallback：

- VLM 超时：使用 ROI 路径和检测类别生成规则描述。
- 视频理解超时：`video_summary=null`，说明未执行。
- LLM 超时：使用模板生成 `llm_explanation`。
- JSON 非法：保留原始输出，使用 schema-safe 模板重建。

`fallback_status` 必须字段化：

```json
{
  "detector": "ok|failed|fallback|not_executed",
  "event_trigger": "ok|failed|fallback|not_executed",
  "vlm": "ok|timeout|disabled_by_project4_decision|not_executed|failed",
  "video": "ok|timeout|disabled_by_project4_decision|not_executed|failed",
  "llm": "ok|timeout|template_fallback|failed|not_executed",
  "alarm_json": "ok|schema_repaired|fact_conflict_detected|failed|not_executed"
}
```

## 记录要求

- 每条告警必须关联 event_id。
- 告警 JSON 保存到 `benchmark/raw/05_alarm_system/<board>/alarms/`。
- schema 校验结果保存到 `benchmark/processed/05_alarm_system/`。
- 不合格输出进入 `projects/05_alarm_system/reports/troubleshooting.md`。
- `projects/05_alarm_system/reports/failure_and_fallback.md` 必须记录 fallback 策略和触发次数。

## 输出文件

| 文件 | 要求 |
|---|---|
| `benchmark/raw/05_alarm_system/<board>/alarms/*alarm_json*.jsonl` | 告警 JSON |
| `benchmark/processed/05_alarm_system/*alarm_schema_check.md` | schema 校验报告 |
| `logs/runtime/05_alarm_system/<board>/*alarm_json*.log` | 生成日志 |
| `logs/failures/05_alarm_system/<board>/*json*.log` | 非法输出或冲突记录 |
| `projects/05_alarm_system/reports/event_pipeline.md` | JSON 在链路中的位置和字段 |
| `projects/05_alarm_system/reports/failure_and_fallback.md` | fallback 记录 |

## 验收标准

- JSON 可被 schema 校验。
- 必须字段不缺失。
- LLM 输出不能覆盖原始检测事实。
- fallback 状态明确。
- 每条 JSON 都能追溯到 event package、模型输出、日志和项目四准入引用。

## 降级和问题库

下面问题必须进入 `projects/05_alarm_system/reports/troubleshooting.md`：

- JSON 不合法。
- 字段缺失。
- 解释与检测事实冲突。
- LLM 输出无法解析。
- fallback 状态缺失。
- 告警 JSON 无法追溯 event_id 或 raw result。
