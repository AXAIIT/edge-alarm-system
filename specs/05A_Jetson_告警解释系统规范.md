# 05A_Jetson_告警解释系统规范

## 适用范围

本规范用于在 Jetson 8GB 上运行项目五完整告警解释系统主线：

```text
YOLO11n TensorRT 高频检测
-> 事件触发 / ROI / 短视频片段
-> Qwen3-1.7B GGUF Q4_K_M 低频/异步文本解释
-> Qwen3-VL-2B 关键帧/ROI 低频问答路线；只有真实 ROI 图片和模型调用完成后才算 VLM 执行
-> 视频理解按项目四准入启用；当前 Jetson SmolVLM2 多帧视频为 D_not_used
-> 结构化告警 JSON
-> 端到端 benchmark 和稳定性监控
```

Jetson 是项目五的检测、文本解释和低频 ROI 图文解释主展示平台，但仍必须遵守项目四准入等级：项目四没有判为 A/B 的模型，不能在项目五写成在线能力。当前项目四结论要求 Jetson 文本 LLM 和图文 VLM 都只能按 `B_low_frequency` 低频/异步接入，SmolVLM2 多帧视频理解为 `D_not_used`。

告警业务语义以 `projects/05_alarm_system/specs/05H_告警业务语义与事件规则规范.md` 为准。Jetson 第一阶段直接由 YOLO 检测触发的 `visual_detection` 候选告警只包含 `person_presence`、`vehicle_presence`、`multi_object_scene` 三类；同时还必须支持 `visual_evidence`、`text_explanation`、`system_runtime`、`model_runtime`、`json_quality`、`video_fallback` 等解释和降级任务的结构化记录。不得把旧版 `generic_object_event` 或任意检测框触发写成正式业务告警。

Jetson 本阶段的系统任务是：在保持 YOLO11n TensorRT 高频检测不被阻塞的前提下，把检测结果转化为候选事件包，并对候选事件生成低频文本解释、可选 ROI 图文复核、结构化告警 JSON 和完整 benchmark 记录。

项目四的 `B_low_frequency` 只说明模型可以作为低频/异步路线进入项目五设计，不等同于项目五已经完成真实事件 ROI 复核。项目五报告必须同时说明 `model_execution.llm_execution`、`model_execution.vlm_execution` 和对应 raw/log；template 文本输出、VLM route stub 或缺失 ROI 图片资产时，状态只能写 `not_verified`、`stub` 或 `not_executed`。

Jetson 最终系统目标按 `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` 执行：YOLO DetectorService 必须常驻，事件队列必须异步有界，Qwen3 文本和 Qwen3-VL 只能低频消费事件，不能同步阻塞检测。当前 `run_detector_adapter.py`、`run_llm_explain.py` 和 `run_vlm_roi_qa.py` 串联结果只能证明 post-detector chain 或 single-shot model smoke；只有完成 05K 的 resident service smoke/required，才能写成完整在线告警服务。

截至 `2026-07-17`，Jetson 当前正式收口拓扑已经固定为：

| 层级 | 正式拓扑 | 当前状态 | 说明 |
|---|---|---|---|
| 实时检测 | `resident detector` | 已通过 | 对应 `run_jetson_p4_resident_detector_smoke.sh` |
| 实时文本解释 | `resident text` | 已通过 runtime 复用 | 对应 `run_jetson_p6_resident_text_smoke.sh` 与 Route B realtime |
| 实时 VLM | `stub` | 正式主线不启用真实 VLM | Jetson 不再把同窗三常驻作为默认验收主线 |
| 低频视觉补充 | `postrun async VLM enrichment` | 已通过 | 对应 `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1` |
| 单板 target | `Route B postrun target` | 已通过 | 对应 `20260717_jetson_8gb_alarm_service_route_b_target_v3` |
| 旧同窗三常驻 | `detector + text + resident VLM same-window` | 仅保留诊断意义 | 不能替代当前正式验收路线 |

### 文本事实约束与发布后验校验

Jetson resident text 的原始模型输出不能直接视为可发布告警解释。Project5 在 `build_alarm_json.py` 最终写入 Alarm JSON 前执行 `fact_guard.py`：要求四段输出契约，检查风险等级、目标类别和显式置信度是否与 event package 一致，并拒绝安全帽、跌倒、火焰、烟雾、打架、异常行为等当前三类 presence 事件无法证明的行为或场景属性。

当校验失败时，系统保留 `llm_raw_output` 供审计，但用 detector facts 生成四段安全模板写入 `llm_explanation`，并设置 `json_fact_conflict=true`、`fact_conflict_detail` 和 `fallback_status.alarm_json=fact_conflict_detected`。因此模型漂移不会污染最终告警；语义验收必须同时证明真实 LLM 复用、Alarm JSON schema pass 和这一后验校验的替换行为正确。

`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` 已完成上述板端验收。Qwen3-1.7B 在 `TEXT_DEVICE=none`、`QWEN_NO_THINK=1` 下由同一 resident server（`pid=1901315`、`model_load_count=1`）连续处理 3 个真实事件；三条原始输出均没有 thinking 内容，但分别出现风险等级不匹配或检测事实外断言。最终 3 条 Alarm JSON 均正确记录 `json_fact_conflict=true` 和具体冲突原因，发布文本全部替换为 detector-fact 四段模板，3 条 Alarm JSON schema 均为 pass。该结果证明的是**发布侧约束有效**，不是“原始 Qwen3 文本无需约束即可直接发布”。

| 检查项 | v3 实测值 | 规范判定 |
|---|---:|---|
| resident model load count | `1` | pass |
| resident request index | `1/2/3` | pass |
| no-think 原始输出 | `3/3` | pass |
| 原始文本事实冲突 | `3/3` | 允许，必须隔离 |
| publishable 文本替换 | `3/3` | pass |
| Alarm JSON schema | `3/3 pass` | pass |

代码边界按 `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md` 执行。项目三 Jetson pipeline 和项目四 Jetson 模型准入可以作为 evidence/artifact 继承；最终 Project5 服务入口、队列、worker 和 AlarmSink 必须在项目五目录内实现。当前分步流程仍主要是 replay/single-shot，不能写成 `independent_runtime_pass`。

Jetson 从当前分步证据到最终系统必须按 `projects/05_alarm_system/specs/05M_常驻告警系统实施路线图.md` 的 P4、P5、P6、P7、P8 顺序执行：先编译并运行 Project5 本地 TensorRT detector 的 10 分钟 template/stub smoke，再补服务内 ROI 资产，再实现本地常驻/warm LLM/VLM worker，最后进行 10 分钟和 30 分钟全链路验收。任何 single-shot 结果只可作为 P1 证据，不能跳过前述阶段。

当前 Jetson 的 P7/P8 正式推进口径也已经明确：

1. `P7 realtime`：`detector resident + resident text + VLM stub`
2. `P7 dual-service`：在同一 `RUN_ID` 下完成 realtime lane，并以 `postrun` 方式补跑 async VLM enrichment
3. `P8 required`：沿用同一拓扑，不再把 resident VLM 同窗并发作为默认必过条件
4. `P9 target`：沿用同一拓扑，以 `VLM_ONCE_PREWARM_REQUEST=1` 与 `VLM_ONCE_PREWARM_MAX_TOKENS=8` 固化 Jetson 单板 2 小时 accepted 路线

Jetson 输出必须能说明：

| 问题 | 必须给出的证据 |
|---|---|
| 为什么触发？ | `alarm_domain`、`alarm_type`、`trigger_rule_id`、`trigger_reason` |
| 触发对象是什么？ | `detections`、`class_name`、`confidence`、`bbox` |
| 视觉证据在哪里？ | `keyframe_path`、`roi_paths`、`roi_boxes`、`video_clip_path` |
| 模型解释是什么？ | Qwen3-1.7B 文本解释，Qwen3-VL 低频 ROI 复核或 fallback |
| 系统是否可靠？ | schema check、fact conflict、latency、resource、fallback、stability |

## 执行原则

下面步骤是推荐路径，不是唯一实现。可以替换服务框架、模型 runner、队列实现和监控工具，但不能降低证据要求：必须证明高频检测不被 LLM/VLM 阻塞，每个告警可追溯到 event_id、raw result、日志、项目四准入结论和告警 JSON。最终服务化验收以 05K 为准，独立代码边界以 05L 为准；本文件中的分步命令默认只构成模块证据、legacy adapter smoke 或后处理链路证据。

## 路径口径

| 类型 | 路径 |
|---|---|
| 项目配置 | `projects/05_alarm_system/configs/` |
| Jetson 配置 | `projects/05_alarm_system/configs/boards/jetson_8gb.yaml` |
| 模型组合配置 | `projects/05_alarm_system/configs/models/jetson_model_combo.yaml` |
| 事件规则 | `projects/05_alarm_system/configs/event_rules/` |
| 告警 schema | `projects/05_alarm_system/configs/alarm_schema/` |
| run 记录 | `projects/05_alarm_system/runs/<run_id>/run.md` |
| 项目报告 | `projects/05_alarm_system/reports/` |
| raw result | `benchmark/raw/05_alarm_system/jetson_8gb/` |
| processed result | `benchmark/processed/05_alarm_system/` |
| benchmark 日志 | `logs/benchmark/05_alarm_system/jetson_8gb/` |
| runtime 日志 | `logs/runtime/05_alarm_system/jetson_8gb/` |
| monitor 日志 | `logs/monitor/05_alarm_system/jetson_8gb/` |
| failure 日志 | `logs/failures/05_alarm_system/jetson_8gb/` |

## 前置条件

- 项目三 Jetson C++ pipeline 可运行，并有 `projects/03_video_pipeline/reports/runtime_benchmark.md`。
- 项目四 Jetson 模型准入完成，并有 `projects/04_llm_vlm_independent/reports/project5_integration_decision.md`。
- Jetson 上的 Qwen3-1.7B、Qwen3-VL-2B、SmolVLM2 或任何替代模型是否接入，必须能在项目四准入矩阵中找到依据。
- 已准备固定视频或摄像头输入。
- 已准备事件规则、prompt 模板、模型组合配置和告警 JSON schema。
- 已确认事件规则使用 `projects/05_alarm_system/configs/event_rules/jetson_rules.yaml` v2，且 `class_filter` 非空。
- 已建立 Jetson 环境基线，记录 JetPack、CUDA/TensorRT、LLM/VLM runtime、电源模式、散热、swap。
- 环境基线必须对齐 `projects/05_alarm_system/specs/00_environment_baseline_template.md`。
- run 记录必须对齐 `projects/05_alarm_system/specs/00_run_record_template.md`。
- per-event raw 必须符合 `benchmark/schemas/alarm_system_raw_schema.json`。
- event package 必须符合 `benchmark/schemas/alarm_event_package_schema.json`。
- 告警 JSON 必须符合 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json`。

如果项目四报告为空或缺少 Jetson 准入结论，本 spec 只能做接口联调和 mock，不允许写成完整链路验收通过。

## 执行步骤

Jetson 实机执行时优先使用 `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md` 的完整命令序列。本节保留模块级命令和字段要求；05I 负责规定 RUN_ID、前置检查、template/real-model 分流、schema 校验和报告回填顺序。

### 1. 冻结模型组合

新建 `projects/05_alarm_system/runs/<date>_jetson_8gb_alarm_combo_freeze/run.md`，记录：

- YOLO detector artifact。
- 文本 LLM 模型、runtime、量化格式。
- 图文 VLM 模型、调用频率、输入尺寸。
- 视频理解模型、片段长度、采样帧数。
- 项目四准入等级和证据路径。
- 禁用项和原因。

### 2. 启动高频检测链路

推荐命令：

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_detector_adapter.py \
  --board-config projects/05_alarm_system/configs/boards/jetson_8gb.yaml \
  --source <camera_or_video> \
  --project3-config <project3_pipeline_config> \
  --project3-raw <project3_frame_level_jsonl> \
  --output benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_detector_events.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_detector_adapter.log 2>&1
```

如果直接调用项目三 C++ 服务，必须记录服务启动命令、配置、日志和检测 JSON 输出路径。当前 `run_detector_adapter.py` 只负责把项目三 frame-level JSONL 接入项目五链路；没有 `--project3-raw` 时会直接失败，避免误把空 adapter 当成真实检测执行。

### 3. 生成事件包

调用事件触发模块：

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_event_trigger.py \
  --detections benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_detector_events.jsonl \
  --rules projects/05_alarm_system/configs/event_rules/jetson_rules.yaml \
  --output benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_event_trigger.log 2>&1
```

事件包必须包含 event_id、alarm_domain、alarm_type、event_stage、frame_id、timestamp、detections、keyframe_path、roi_paths、video_clip_path。当前第一阶段 `event_stage` 应为 `candidate`，系统状态不得写成完整业务告警验收通过。

### 4. 调用文本 LLM

文本解释用于告警归因和日志解释。默认命令是 template 接口联调；真实 Qwen3 文本解释必须按 05I 使用 `--mode llama_cpp`、`--llama-bin` 和 `--model-path`。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_llm_explain.py \
  --events benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --prompt-template data/prompts/alarm_text_explain.md \
  --output benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_llm_outputs.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_llm_explain.log 2>&1
```

必须记录 first token、prefill、decode tokens/s、total time、prompt tokens、output tokens、memory、swap、temperature。

### 5. 低频调用图文 VLM

图文 VLM 只能按项目四准入等级低频或异步调用，不能逐帧运行。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_vlm_roi_qa.py \
  --events benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --max-events <n> \
  --timeout-ms <timeout> \
  --output benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_vlm_outputs.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_vlm_roi_qa.log 2>&1
```

必须记录 ROI 尺寸、图片预处理耗时、VLM 总耗时、超时次数和 fallback。

当前 `run_vlm_roi_qa.py` 只能记录 ROI/VLM 路由和 fallback 字段；如果 event package 中 `roi_paths` 为空，或没有真实 Qwen3-VL 模型 raw、runtime log、monitor log，则只能写 `vlm_execution=route_stub_only`，不能把结果计入 Qwen3-VL 性能或系统能力结论。

### 6. 视频理解降级或专项复测

当前项目四 selected 结论中，Jetson SmolVLM2 多帧视频理解为 `D_not_used`，不能接入项目五在线或低频链路。项目五默认不调用 `run_video_understanding.py`，`video_summary` 由检测结果、关键帧/ROI 摘要和文本 LLM 规则化生成，告警 JSON 中 `fallback_status.video` 必须写 `disabled_by_project4_decision`。

只有在新增项目四或项目五专项证据后，才允许开启短片段视频理解；届时必须重新写入 run、raw、日志、监控和质量复测结果。参考命令保留如下，不能作为当前 Jetson 主线默认命令：

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_video_understanding.py \
  --events benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --clip-seconds 2 \
  --sampled-frames 4 \
  --timeout-ms <timeout> \
  --output benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_video_outputs.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_video_understanding.log 2>&1
```

仅当新增证据允许启用视频模型时，才必须记录视频解码、采样、预处理、生成耗时和 summary 质量。当前默认主线应在 per-event raw 中将 `video_understanding_total_ms` 记为 `null`，并在告警 JSON 中标注视频模型降级。

### 7. 生成并校验告警 JSON

```bash
python3 projects/05_alarm_system/scripts/run_demo/build_alarm_json.py \
  --events benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  --llm benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_llm_outputs.jsonl \
  --vlm benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_vlm_outputs.jsonl \
  --video none \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --output benchmark/raw/05_alarm_system/jetson_8gb/alarms/<date>_jetson_alarm_json.jsonl \
  > logs/runtime/05_alarm_system/jetson_8gb/<date>_jetson_alarm_json.log 2>&1
```

schema 不合格时必须保留原始输出、修复输出和 fallback 状态。

### 8. 端到端 benchmark

```bash
python3 projects/05_alarm_system/scripts/benchmark/run_alarm_system_benchmark.py \
  --board jetson_8gb \
  --events benchmark/raw/05_alarm_system/jetson_8gb/events/<date>_jetson_event_packages.jsonl \
  --alarms benchmark/raw/05_alarm_system/jetson_8gb/alarms/<date>_jetson_alarm_json.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --output benchmark/raw/05_alarm_system/jetson_8gb/<date>_jetson_alarm_system_benchmark.jsonl \
  > logs/benchmark/05_alarm_system/jetson_8gb/<date>_jetson_alarm_system_benchmark.log 2>&1
```

### 9. Schema 校验

项目五当前提供最小 JSONL schema 校验器，用于检查 event package、alarm JSON 和 per-event raw 的 required 字段：

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input <jsonl> \
  --schema <schema_json> \
  --output benchmark/processed/05_alarm_system/<run_id>_schema_check.md
```

该校验器不替代正式质量评估，只用于阻止字段缺失、检测事实来源错误和 fallback 字段缺失。

## 本地 dry-run 证据

`20260704_jetson_8gb_alarm_system_v3_task_domain_local_check` 使用仓库内项目三 Jetson raw 做了 10 个事件的接口联调，验证新增 `alarm_domain` 后的脚本和 schema 闭环：

| artifact | path | status |
|---|---|---|
| event package | `benchmark/raw/05_alarm_system/jetson_8gb/events/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_events.jsonl` | schema pass, rows=10 |
| LLM template output | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_llm_outputs.jsonl` | stub/template only |
| VLM stub output | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_vlm_outputs.jsonl` | not model execution |
| alarm JSON | `benchmark/raw/05_alarm_system/jetson_8gb/alarms/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_alarms.jsonl` | schema pass, rows=10 |
| per-event raw | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_alarm_system_benchmark.jsonl` | schema pass, rows=10 |

v3 样本按 `alarm_domain/alarm_type` 聚合为 `visual_detection/vehicle_presence=4`、`visual_detection/multi_object_scene=3`、`visual_detection/person_presence=3`。

这轮状态必须解释为 `not_verified` / interface dry-run：未执行项目五 Jetson 并发模型调用、真实 ROI 裁剪、真实短片段生成、monitor 采样和 30 分钟稳定性，不能作为系统验收通过。

后续正式 Jetson run 必须使用 `jetson_alarm_rules_v2_candidate_presence` 并保留 `alarm_domain` 字段。旧 smoke 中由 `generic_object_event` 产生的 542 条记录只能解释为旧 schema/旧规则接口候选事件，不得作为正式告警数量或误报率统计。

## 记录要求

- 每次运行必须新建 `projects/05_alarm_system/runs/<run_id>/run.md`。
- 运行记录必须引用项目三 pipeline 证据和项目四准入证据。
- raw result 保存到 `benchmark/raw/05_alarm_system/jetson_8gb/`。
- 端到端 benchmark raw 必须符合 `benchmark/schemas/alarm_system_raw_schema.json`，不能在本 spec 里单独维护字段清单。
- event package 和 alarm JSON 必须分别通过 `alarm_event_package_schema.json` 和 `alarm_event_schema.json` 校验。
- runtime、benchmark、monitor、failure 日志按路径口径保存。
- 报告必须更新 `board_matrix.md`、`event_pipeline.md`、`llm_vlm_benchmark.md`、`video_understanding_benchmark.md`、`alarm_system_benchmark.md`。
- 失败或降级必须更新 `failure_and_fallback.md` 和 `troubleshooting.md`。

## 输出文件

| 文件 | 要求 |
|---|---|
| `benchmark/raw/05_alarm_system/jetson_8gb/events/*.jsonl` | event package |
| `benchmark/raw/05_alarm_system/jetson_8gb/alarms/*.jsonl` | 告警 JSON |
| `benchmark/raw/05_alarm_system/jetson_8gb/*alarm_system_benchmark*.jsonl` | 端到端 benchmark |
| `logs/monitor/05_alarm_system/jetson_8gb/*` | 资源监控 |
| `projects/05_alarm_system/reports/board_matrix.md` | Jetson 模型组合和项目四准入引用 |
| `projects/05_alarm_system/reports/alarm_system_benchmark.md` | Jetson MLPerf-style Summary |

## Jetson Benchmark 指标表

| 类别 | 必填指标 | 当前继承基线 | 项目五要求 |
|---|---|---|---|
| 检测吞吐 | FPS avg/min/max | 项目三 selected runtime：约 `30.0872 FPS` | 系统整合后记录 FPS delta |
| 检测延迟 | p50/p90/p95/p99、分阶段耗时 | 项目三 runtime p95 `49.1965 ms`、p99 `52.2379 ms` | 记录检测是否被 LLM/VLM 阻塞 |
| 队列 | queue_depth、wait_ms、drop_count、drop_reason | 项目三 detector queue 有基线 | 项目五 event queue 必须独立记录 |
| 事件 | trigger latency、ROI crop latency、video clip latency | 无继承基线 | event package 必填 |
| 告警任务 | candidate_event_count、event_rate_per_min、按 `alarm_domain`/`alarm_type` 聚合 | 无继承基线 | 按 05H 任务域和三类候选告警统计 |
| 文本 LLM | first token、prefill、tokens/s、total、prompt/output tokens | Qwen3-1.7B p95 `6370.1 ms`、decode `29.345 tok/s` | per-event raw 必填 |
| 图文 VLM | image preprocess、VLM total、timeout rate、quality | Qwen3-VL p50 `24120.0 ms`、p95 `33107.15 ms` | 只低频 ROI/关键帧调用 |
| 视频理解 | clip duration、sampled frames、decode/preprocess/generate | SmolVLM2 `D_not_used` | 默认禁用；写明 fallback |
| 告警 JSON | schema pass、fact conflict、repair count、event trace pass | 无继承基线 | alarm JSON 必须校验 |
| 资源 | memory、swap、temperature、power、CPU/GPU util | 项目三/四有单链路基线 | 系统并发必须重新采样 |
| 稳定性 | 10 min smoke、30 min required、120 min target | 项目三检测 2h 已通过 | 项目五系统至少 30 min |

## 验收标准

- Jetson 完成 YOLO 检测、事件包、文本解释、告警 JSON 的完整链路。
- 图文 VLM 只能在真实 ROI/keyframe 资产、真实模型 raw 和日志齐全时写成按项目四 `B_low_frequency` 低频异步启用；否则必须写 `route_stub_only` 或 `not_executed`。视频理解当前按 `D_not_used` 禁用并标记 `disabled_by_project4_decision`。
- Jetson 当前正式 required 路线必须是 `realtime detector + resident text + postrun async VLM enrichment`；`parallel async` 或 `legacy all-resident same-window` 只保留诊断意义，不能替代正式验收。
- 高频检测不被 VLM/LLM 阻塞，检测 FPS、队列长度和 drop count 有记录。
- 告警 JSON 通过 schema 校验，且 LLM 输出不覆盖原始检测事实。
- 端到端耗时、LLM/VLM 耗时、内存、swap、温度、功耗或电源模式完整。

## 降级和问题库

下面问题必须进入 `projects/05_alarm_system/reports/troubleshooting.md`：

- 项目四 Jetson 准入证据缺失。
- VLM 或视频理解阻塞检测链路。
- LLM 输出非 JSON 或与检测事实冲突。
- event_id、frame_id、ROI 或视频片段无法追溯。
- Jetson 温控降频、内存不足、swap 异常。
- 模型超时、服务崩溃或无法恢复。
