# 05_双板边缘LLM_VLM告警解释系统

## 2026-07-18 最新验收结论（覆盖下方历史阶段记录）

项目五 runtime 主线已完成双板 `P9 target` 验收。`20260717_p05_dual_board_target_v1` 采用 Jetson accepted Route B（resident detector + resident text + postrun async VLM）和 RK3588 同窗 resident detector + resident text + resident VLM：Jetson `window_sec=7217.22`、`detection_fps=30.000887`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`；RK3588 `window_sec=7203.72`、`detection_fps=30.042395`、`event_count=765`、`alarm_count=765`、`llm_call_count=2`、`vlm_call_count=2`、`drop_count=0`。两板启动差 `22.5s`、有效重叠 `7194.72s`，超过 `6900s` 门槛，组级结果为 `dual_board_target_ready`。组级证据固定为 `benchmark/processed/05_alarm_system/20260717_p05_dual_board_target_v1_dual_board_summary.{json,md}`。

因此，本文下方涉及“Jetson P7/P8、双板 P9 或双板 target 待完成”的历史描述仅保留为问题演进记录，不能作为当前结论。`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` 已关闭 Jetson resident text 的发布侧事实守卫项：同一模型加载完成三次真实 no-think 请求，三条原始冲突文本均保留审计并被安全替换为 detector-fact 告警。Jetson legacy same-window resident VLM request path 仅保留为诊断分支，不阻塞已接受的 Route B 方案。

规范状态：v1.3 独立代码库、常驻服务边界与实施路线图补充版。当前项目五主线收敛为 Jetson 8GB 和 RK3588 8GB 双板实验；RDK X5 因项目四准入失败，从项目五主线实验、横向 benchmark 和稳定性验收中移除。当前已补齐项目五专用 run 模板、环境基线模板、per-event raw schema、time-window stability schema、event package schema、告警 JSON schema、输入源 manifest、模型组合 schema、统一 05G 汇总规范、告警业务语义规范、目录式 run 结构、最新有效 run 选择规则、PC 调试限制、服务记录字段、队列指标约束、MLPerf-style 报告模板、05K 常驻服务验收、05L 独立代码库边界规范和 05M 实施路线图。

当前实测状态：Jetson 已完成视频端 required 30min 后处理链路、IMX219 摄像头 detector smoke，以及 Project5 本地 resident detector 10 分钟 smoke：`20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` 给出 `window_sec=612.629`、`detection_fps=29.458286`、`event_count=136`、`alarm_count=136`、`drop_count=0`，并已从同步回传的 `tegrastats` 回填出 `memory_mb=2146.0`、`swap_used_mb=195.0`、`temperature_c=50.0`，可声明 `resident_detector_smoke_pass_with_template_stub_workers`。随后 `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` 又补齐了 Jetson P6 resident text worker：`window_sec=74.571`、`events=3`、`alarms=3`、`llm_rows=3`、`llm_bad_rows=0`，同一 `resident_server_pid=3828920`、`resident_model_load_count=1`、`resident_request_index=1/2/3`，可声明 `resident_text_worker_smoke_pass`。Jetson resident VLM 也已拿到正式板端通过证据：`20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 在更保守的 CPU-first 参数下实现 `vlm_rows=3`、`vlm_bad_rows=0`、同一 `resident_server_pid=4611`、`resident_model_load_count=1`、`resident_request_index=1/2/3`，证明 standalone resident VLM 已经成立。但 Jetson 单板 P7 仍未通过：最新 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 已进入有效 10 分钟窗口，`window_sec=630.325`、`requested_window_sec=600.0`、`window_requirement_met=true`、`detection_fps=28.632848`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=2`、`event_queue_depth=91`、`drop_count=0`，且 text resident 保持同一 `resident_server_pid=60424`、`resident_model_load_count=1`；但 resident VLM 两次真实请求仍失败，第 1 条为 `RemoteDisconnected`，第 2 条为 `timeout`，因此当前 Jetson 主阻塞点已经从 startup OOM、detector 冷启动失败和 queue 打满，进一步收口为 resident multimodal request path。P7/P8 wrapper 现已固定使用 `TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1`、`TEXT_DEVICE=none`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、`DETECTOR_START_ORDER=after_workers`、`SERVICE_QUEUE_CAPACITY=192` 和更小的 text/VLM token budget；`-ngl 0` 本身并不保证完全不占 GPU，因此这里还额外关闭 KV cache offload，并把 text resident 显式固定到 CPU-only 设备，目的就是先把 Jetson 单板并发窗口稳定到“detector 不被 LLM/VLM 启动阶段挤掉，真实请求问题单独暴露”。RK3588 已完成视频端 required interface 30min、真实 RKLLM 文本解释 smoke、Astra S OpenNI 摄像头 alarm-chain smoke，并已完成 `SAVE_OUTPUT_VIDEO=1` + ROI 资产抽取 + Qwen3-VL RKNN/RKLLM single-shot runtime 路线 smoke。两板视频理解模型均按项目四结论禁用；RK3588 当前 VLM 不再只是 single-shot 路线证据，而是已经补齐 Project5 本地 resident VLM worker smoke：`20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` 生成 `vlm_rows=3`、`vlm_bad_rows=0`，同一 `resident_server_pid=2436647`，`resident_model_load_count=1`，`resident_request_index=1/2/3`，且 event/alarm/per-event/stability 四类 schema 全部 pass。代码边界方面，当前已把 RKLLM text/VLM 默认 wrapper 迁到 Project5 本地 runtime adapter，并新增 Project5 本地 service skeleton；service 入口已支持 `resident_process`、detector replay、`--events-input`、worker mode、call budget、Project5 本地 `AssetWorker`、Jetson 侧 `llama_cpp_resident` 文本 worker，以及 Jetson 侧 `llama_cpp_multimodal_resident` VLM worker；`project5_code_boundary_check.md` 已给出 `independent_runtime_pass`。B 方案入口层已实现：service 可以启动 Project5 本地 detector 进程、tail detector JSONL、触发事件并持续写 Alarm JSON；Project5 本地 detector 源码和双板 build 脚本已就位，RK3588 本地 RKNN detector runner 已于 `20260709_rk3588_8gb_p05_detector_build_v1` 编译成功，并已在 `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` 完成真实 10 分钟 `resident_process` 运行；随后又在 `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1` 证明了 Project5 本地 `rkllm_resident` 文本 worker 的一次加载多次请求复用，并在 `20260710_rk3588_8gb_alarm_service_asset_worker_smoke_v1` / `v2` 完成了 Project5 本地 AssetWorker 的板端视频回放 smoke。该 AssetWorker smoke 明确使用 `video_playlist` 回放补齐 `keyframe_path`/`roi_paths`，不是摄像头在线资产链路。最新代码已进一步补入 detector-side `frame_cache_dir` 机制：Project5 本地 detector 现在可以按 `frame_id` 写 bounded JPEG ring，供 service 在 camera/RTSP 场景回填同源帧资产；`20260711_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1` 已经补齐了第一条 camera/RTSP frame-cache asset smoke pass。更进一步，RK3588 已用收敛参数 `FRAME_CACHE_CAPACITY=512`、`SERVICE_QUEUE_CAPACITY=32`、`DETECTOR_QUEUE_CAPACITY=16`、`CLEAN_FRAME_CACHE_ON_EXIT=1` 完成最新一轮单板常驻 service 收口：`20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` 给出 `window_sec=603.714`、`detection_fps=29.89495`、`event_count=75`、`alarm_count=75`、`llm_call_count=2`、`vlm_call_count=2`、`event_queue_depth=19`、`drop_count=0`，并回填 `memory_mb=6015.0`、`swap_used_mb=483.5`、`temperature_c=58.23`；`20260713_rk3588_8gb_alarm_service_resident_required_v2` 又把同一链路扩展到单板 30 分钟 required，`window_sec=1803.685`、`detection_fps=30.010783`、`event_count=200`、`alarm_count=200`、`llm_call_count=2`、`vlm_call_count=2`、`event_queue_depth=24`、`drop_count=0`，并回填 `memory_mb=6052.8`、`swap_used_mb=484.0`、`temperature_c=62.85`；最终 `20260713_rk3588_8gb_alarm_service_resident_target_v2` 完成单板 2 小时 target，`window_sec=7204.045`、`requested_window_sec=7200.0`、`window_requirement_met=true`、`detection_fps=30.054365`、`event_count=765`、`alarm_count=765`、`llm_call_count=2`、`vlm_call_count=2`、`event_queue_depth=23`、`drop_count=0`，并回填 `memory_mb=6066.1`、`swap_used_mb=484.2`、`temperature_c=62.85`。这说明 RK3588 当前已经形成最新有效的单板 P7/P8/P9 证据，同时后续 run 不再保留整窗 `frame_cache` JPG，而是只保留少量真实 VLM 所需资产并在退出时清理缓存。当前真正未完成的主缺口已收敛为：Jetson resident VLM request path 收口、Jetson 单板 P7/P8 通过判定，以及双板 P9 target 收口。为消除跨项目依赖，Project5 现已补入本地 RKLLM 文本 runner、resident text server、resident VLM server、Jetson `llama-server` resident text/VLM client、AssetWorker 源码、detector-side frame cache 和 service 接入位；其中 Jetson resident text、Jetson resident VLM standalone、Jetson P7 有效时间窗、RK3588 resident text、RK3588 resident VLM、视频回放 AssetWorker、camera frame-cache asset path、单板 P7 并发 smoke、单板 P8 required 和单板 P9 target 均已有实测证据，但仍不能把两板写成完整在线常驻告警服务已完成。

2026-07-14 补充更新：Jetson 的分层收口路线已经拿到第一轮正式结果。Route A `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` 证明在 live detector 压力下，`resident detector + resident VLM + template text` 可以维持 `window_sec=676.324`、`requested_window_sec=600.0`、`window_requirement_met=true`、`detection_fps=26.685435`、`event_count=136`、`alarm_count=136`、`llm_call_count=0`、`vlm_call_count=2`、`drop_count=0`，但两次真实 VLM 请求都退化为 `llama_cpp_multimodal_resident_request_failed_stub_fallback`，错误统一为 `timeout: timed out`，因此 Route A 仍未通过。Route B realtime `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` 则已经跑通 `resident detector + resident text + VLM stub`：`window_sec=612.872`、`detection_fps=29.448237`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`，同一 `resident_server_pid=343498`、`resident_model_load_count=1`、请求序号 `1/2` 递增，说明 Jetson 的实时主链路已经可以收口到 `detector + resident text`。但该 run 也暴露了新的业务正确性问题：第 2 条真实文本解释把 `vehicle_presence/car` 错写成“未佩戴安全帽”，说明 Route B 当前只能声明运行时链路通过，不能直接声明解释语义已验收。Route B async enrichment `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 又进一步证明，把 VLM 从实时链路拆到第二条 service run 之后，真实图片请求仍然在 `events_input + resident VLM` 路径上两次 timeout；因此 Jetson 当前真正稳定成立的是 `detector + resident text` 实时主链路，而 Jetson resident VLM 的主阻塞点已经被精确收口为 multimodal request path 本身，而不再是 resident text 干扰或 queue backpressure。基于这个结论，Project5 现已补入 `run_async_vlm_enrichment.py` 与 `run_jetson_p7_route_b_dual_service_smoke.sh`，把 B 方案正式落成“realtime detector+text + 独立 async VLM worker”的双进程结构。

同日第二轮补充更新：在 `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v3` 首次拿到 async VLM 真实 pass 后，`20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4` 又把 B 方案推进到“最新运行证据齐全”的阶段。与 `v3` 相比，realtime 路线继续稳定维持 `window_sec=627.353`、`requested_window_sec=600.0`、`window_requirement_met=true`、`detection_fps=28.741394`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`，且这次 `restart_count=0`。与此同时，async VLM worker 仍然给出 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`，但成功行已不再依赖 `retry1`：`vehicle_presence` 这条 pass 直接记录 `resident_retry_count=0`、`resident_server_pid=503522`、`resident_model_load_count=1`、`resident_request_index=1`、`vlm_total_ms=229011.465`。另一条 `person_presence` 仍在 `once_attempts=2` 后失败，不过错误已从单纯 `timeout` 收口为 `RemoteDisconnected: Remote end closed connection without response`。此外，`v4` 的 async enriched alarm / enriched benchmark / realtime stability schema 均已 `pass`。因而 Jetson 当前最新收口结论是：B 方案双进程架构成立、实时主链路稳定、async VLM 持续停留在 `1/2 pass`，剩余主阻塞点已经缩小到 multimodal request path 的事件级稳定性；同时成功行 `vlm_summary` / `vlm_raw_output` 还暴露了中文乱码这一新的产物质量问题。

补充更新（`2026-07-13` latest）：

- Jetson resident VLM 不再是“只有代码、没有板端结果”。`20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已证明 standalone multimodal `llama-server` 能稳定复用：`vlm_rows=3`、`vlm_bad_rows=0`、同一 `resident_server_pid=4611`、`resident_model_load_count=1`、请求序号 `1/2/3`。
- Jetson 单板 P7 当前也不应继续被写成“尚未进入有效窗口”。最新 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 已满足 `window_requirement_met=true`，并把 `drop_count` 从 `99` 收口到 `0`；当前失败层级已前移到 resident VLM request path，而不是 worker startup、detector 冷启动或 queue backpressure。
- Jetson P6 standalone 与 Jetson P7/P8 并发 wrapper 不是同一组默认值。P6-v4 是更保守的 standalone VLM 收口口径；P7/P8 则固定为 `TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1`、`TEXT_DEVICE=none`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、`DETECTOR_START_ORDER=after_workers`、更大的 `SERVICE_QUEUE_CAPACITY` 和更小的 text/VLM token budget，目的是在有效时间窗内把 detector、text、VLM 三层失败分离出来。
- `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` 与 `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 进一步证明：Jetson resident VLM 的 timeout 不是 resident text 干扰造成的偶发现象。无论是 live detector + template text 的 Route A，还是 `events_input + resident VLM` 的第二条 service run，真实图片请求都仍会在 multimodal request path 上 timeout。当前新增的 `run_async_vlm_enrichment.py` / `run_jetson_p7_route_b_dual_service_smoke.sh` 不是在否认这个结论，而是在工程上把 VLM 从实时链路彻底拆出去，先让系统主链路成立，再继续单独收口 Jetson VLM。
- `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` 已经把 Jetson 实时主链路收口到 `detector + resident text + VLM stub`，但该 run 的第 2 条真实文本解释出现了“`vehicle_presence/car` -> 未佩戴安全帽”的事实漂移，因此当前应把 Jetson text 标成“runtime pass with semantic-quality caveat”，而不是“解释语义已完全通过”。

## 定位

本文件是项目五的总规划书和操作参考书。项目五不是重新验证 LLM/VLM 模型能不能跑，也不是把项目三和项目四脚本串成命令清单；而是在项目一、项目三、项目四已经形成证据的基础上，在 `projects/05_alarm_system/` 内形成独立代码边界，把实时检测、事件触发、低频多模态解释、文本告警归因和结构化输出整合成一个可复现的端侧系统。

项目五的核心链路：

```text
摄像头 / 固定视频 / RTSP
-> 项目三 C++ 实时 YOLO11n pipeline
-> 事件触发、抽帧、ROI、短视频片段
-> 项目四准入模型：文本 LLM / 图文 VLM / 视频理解模型
-> 结构化告警 JSON
-> 端到端 benchmark、稳定性监控、问题库
```

上图表示证据继承和系统能力来源，不表示最终运行时可以直接耦合项目三/项目四脚本。最终服务形态必须遵守 `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md`：前序项目可以作为 artifact、raw、报告和模型准入来源；Project5 服务入口、队列、worker、AlarmSink 和最终运行编排必须在 Project5 目录内实现。

## 系统任务

项目五要完成的任务是：在边缘开发板上，把项目三的实时 YOLO 检测结果、项目四验证过的文本/图文解释能力、运行日志和 JSON 质量检查整合成“可追溯、可解释、可结构化输出、可 benchmark”的告警解释结果。

系统不是简单地回答“画面里有什么”，也不是重新训练一个安防大模型。它的任务是围绕检测事实和系统证据完成下面闭环：

```text
检测事实
-> 候选告警事件
-> 视觉证据资产
-> LLM/VLM 解释
-> 结构化告警 JSON
-> 性能、资源、稳定性和失败降级记录
```

项目五统一用 `alarm_domain` 表示任务域，用 `alarm_type` 表示具体告警或解释任务：

| alarm_domain | 系统要做的事 | 当前项目五状态 |
|---|---|---|
| `visual_detection` | 把项目三 YOLO 检测事实转成候选视觉告警事件 | 第一阶段主线 |
| `visual_evidence` | 用项目四准入的图文 VLM 对 ROI、关键帧、面板或异常图片低频复核 | Jetson/RK3588 均只能低频异步 |
| `text_explanation` | 用文本 LLM 解释检测 JSON、告警原因、风险等级和建议动作 | Jetson/RK3588 均为低频异步 |
| `system_runtime` | 解释视频源、检测 pipeline、队列和服务故障 | 项目五稳定性和问题库必填 |
| `model_runtime` | 解释 LLM/VLM timeout、OOM、runtime 不支持和禁用原因 | 项目四失败结论必须继承 |
| `json_quality` | 记录 schema、JSON 修复和检测事实冲突 | alarm JSON 和 benchmark 必填 |
| `video_fallback` | 在视频模型未准入时记录替代摘要策略 | Jetson/RK3588 当前均禁用 SmolVLM2 视频主线 |

第一阶段由项目三检测结果直接触发的候选视觉告警定义为：

| 任务 | 输入 | 系统应输出 | 当前支持状态 |
|---|---|---|---|
| 人员出现候选告警解释 | YOLO 检测到 `person` | 人员数量、位置、置信度、触发帧、候选风险说明、结构化 JSON | `candidate/not_verified` |
| 车辆出现候选告警解释 | YOLO 检测到 `car/bus/truck/motorcycle/bicycle` | 车辆类型、数量、位置、置信度、触发帧、结构化 JSON | `candidate/not_verified` |
| 多目标场景候选告警解释 | 同一事件中出现多个人员/车辆目标 | 场景目标摘要、主要目标列表、触发原因、结构化 JSON | `candidate/not_verified` |

第一阶段不声明已经实现人员入侵、越界、徘徊、聚集、跌倒、烟火等强业务告警。原因是这些任务需要 zone、tracking、专用类别、姿态/动作模型或人工标注固定事件集支撑。缺少这些证据时，系统只能输出候选告警解释，不能写成 verified alarm。

## 当前完成矩阵

| board | run_id | input | detector | events | text LLM | VLM | Alarm JSON / raw | stability | status |
|---|---|---|---|---:|---|---|---|---|---|
| Jetson 8GB | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | `video_set_runtime_v1` | 54130 frames, 30.0722 FPS, schema/trace pass | 397 | real Qwen3 llama.cpp rows=10, bad=0 | route stub rows=3 | 397 rows, schemas pass | time-window raw pass, monitor captured | `pass_with_vlm_stub_and_video_disabled` |
| Jetson 8GB | `20260708_jetson_8gb_alarm_system_camera_imx219_smoke_v1` | IMX219 CSI | 5676 frames, 47.3 FPS, schema/trace pass | 0 | not called | not called | not generated | not applicable | `camera_detector_input_pass_no_alarm_event` |
| Jetson 8GB / resident detector smoke | `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` | Project5 local resident detector, `video_set_runtime_v1` playlist paced 600s | Project5 ResidentProcessDetectorService | 136 | template rows=136, `llm_call_count=0` | stub route, `vlm_call_count=0` | 136 rows, four schema families pass | stability raw `window_sec=612.629`, `window_requirement_met=true`, `drop_count=0`, `event_queue_depth=3` | `resident_detector_smoke_pass_with_template_stub_workers` |
| Jetson 8GB / resident text smoke | `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` | `--events-input` from Project5 validated events | detector skipped; consume Project5 event package | 3 | resident llama.cpp rows=3, same `resident_server_pid=3828920`, `resident_model_load_count=1`, request index `1/2/3` | stub route, real VLM not called | 3 rows, four schema families pass | stability raw `window_sec=74.571`, `llm_call_count=3`, `drop_count=0`; proves one-load multi-request reuse | `resident_text_worker_smoke_pass` |
| Jetson 8GB / resident VLM smoke | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` | `--events-input` from Project5 validated events + service-side asset replay | detector skipped; consume Project5 event package | 3 | template fallback, `llm_call_count=0` | resident llama.cpp rows=3, `vlm_bad_rows=0`, same `resident_server_pid=4611`, `resident_model_load_count=1`, request index `1/2/3` | 3 rows, four schema families pass | stability raw `window_sec=465.22`; proves standalone resident multimodal worker can finish repeated requests after one load | `resident_vlm_worker_smoke_pass` |
| Jetson 8GB / resident service concurrency smoke | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` | Project5 local resident detector + detector-side `frame_cache_dir` + `video_set_runtime_v1` paced 600s | Project5 ResidentProcessDetectorService + resident llama.cpp text worker + resident VLM worker | 136 | resident llama.cpp rows=136, `llm_pass_rows=2`, same `resident_server_pid=60424`, `resident_model_load_count=1`, request index `1/2` | resident VLM rows=136, `vlm_pass_rows=0`, `vlm_bad_rows=2`; first request `RemoteDisconnected`, second request `timeout` | 136 rows, four schema families pass; service log `queue_dropped=0`, `asset_success=2` | stability raw `window_sec=630.325`, `requested_window_sec=600.0`, `window_requirement_met=true`, `detection_fps=28.632848`, `event_queue_depth=91`, `drop_count=0`, `memory_mb=4866.0`, `swap_used_mb=2304.0`, `temperature_c=60.5`, monitor rows=648 | `valid_window_but_resident_vlm_request_failed` |
| Jetson 8GB / Route A detector+VLM | `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` | Project5 local resident detector + `video_set_runtime_v1` paced 600s | Project5 ResidentProcessDetectorService + resident llama.cpp VLM worker + template text | 136 | template rows=136, `llm_call_count=0` | resident VLM rows=136, `vlm_pass_rows=0`, `vlm_bad_rows=2`; both real image requests timeout and fall back | 136 events / 136 alarms / 136 benchmark rows written | stability raw `window_sec=676.324`, `requested_window_sec=600.0`, `window_requirement_met=true`, `detection_fps=26.685435`, `event_queue_depth=134`, `drop_count=0`, `memory_mb=4196.0`, `swap_used_mb=1140.0`, `temperature_c=62.5` | `route_a_valid_window_but_vlm_request_timeout` |
| Jetson 8GB / Route B realtime | `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` | Project5 local resident detector + `video_set_runtime_v1` paced 600s | Project5 ResidentProcessDetectorService + resident llama.cpp text worker + VLM stub | 136 | resident llama.cpp rows=136, `llm_pass_rows=2`, same `resident_server_pid=343498`, `resident_model_load_count=1`, request index `1/2` | stub rows=136, `vlm_call_count=0` | 136 rows, four schema families pass | stability raw `window_sec=612.872`, `requested_window_sec=600.0`, `window_requirement_met=true`, `detection_fps=29.448237`, `event_queue_depth=28`, `drop_count=0`, `memory_mb=3211.0`, `swap_used_mb=1140.0`, `temperature_c=57.5` | `route_b_realtime_runtime_pass_with_text_fact_drift_caveat` |
| Jetson 8GB / Route B async VLM enrichment | `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` | `--events-input` from Route B realtime + `video_set_runtime_v1` asset replay | detector skipped; consume Project5 event package | 3 | template rows=3, `llm_call_count=0` | resident VLM rows=3, `vlm_pass_rows=0`, `vlm_bad_rows=2`; both real image requests timeout and fall back | 3 events / 3 alarms / 3 benchmark rows written | stability raw `window_sec=649.15`, `vlm_call_count=2`, `drop_count=0`; proves timeout reproduces outside realtime text chain | `route_b_async_vlm_timeout_reproduced` |
| Jetson 8GB / Route B dual-service | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4` | Project5 local resident detector + resident text realtime lane + async VLM worker under same `RUN_ID` | realtime lane uses Project5 ResidentProcessDetectorService + resident llama.cpp text worker + VLM stub; second process tails `events.jsonl` and runs `llama_cpp_multimodal_once` with `VLM_REQUEST_RETRIES=1` | 136 realtime events; async budget=2 | realtime resident text rows=136, `llm_pass_rows=2`, same `resident_server_pid=502459`, `resident_model_load_count=1`, request index `1/2` | async VLM rows=2, `async_vlm_pass_rows=1`, `async_vlm_fallback_rows=1`; `vehicle_presence` 直接 pass 且 `resident_retry_count=0`、`vlm_total_ms=229011.465`，`person_presence` 仍在 `once_attempts=2` 后报 `RemoteDisconnected` | realtime event/alarm/benchmark/stability 与 async enriched alarm/benchmark 均写出且 schema pass；async worker 不再在首条后崩溃，真实 VLM pass 也不再依赖 retry1，但成功行文本仍出现乱码 | realtime stability raw `window_sec=627.353`, `detection_fps=28.741394`, `event_queue_depth=36`, `drop_count=0`, `restart_count=0`, `memory_mb=4589.0`, `swap_used_mb=2480.0`, `temperature_c=60.0`; proves Route B architecture and runtime evidence are complete, while async VLM remains partial-success only | `route_b_dual_service_runtime_pass_async_vlm_partial_pass_v4` |
| RK3588 8GB | `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | `video_set_runtime_v1` | 54130 frames, 30.0722 FPS, schema/trace pass | 200 | template rows=10 | route stub rows=3 | 200 rows, schemas pass | time-window raw pass, monitor captured | `required_interface_schema_pass_not_real_rkllm` |
| RK3588 8GB | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | reused required events | reused required detector | 200 | real RKLLM rows=3, bad=0, contaminated=0 | route stub rows=3 | 200 rows, schemas pass | no independent stability raw | `rkllm_text_smoke_pass` |
| RK3588 8GB | `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | Astra S OpenNI `2bc5/0402` | 17762 frames, 29.6033 FPS, schema/trace pass | 2 | real RKLLM rows=2, bad=0, contaminated=0 | route stub rows=2 | 2 rows, schemas pass | no Project5 time-window raw | `camera_alarm_chain_smoke_pass_with_vlm_stub` |
| RK3588 8GB | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` | `video_set_runtime_v1`, `SAVE_OUTPUT_VIDEO=1` | 18048 frames, Project3 pass | 75 raw events; 3 with ROI assets | template fallback only in this VLM smoke | Qwen3-VL RKNN/RKLLM mt384 rows=3, pass=3; previous 128-token truncation fixed by mt384 rerun | Alarm JSON rows=3, schema pass; per-event raw rows=3, schema pass | no Project5 stability raw | `single_shot_vlm_runtime_smoke_mt384_alarm_json_per_event_schema_pass` |
| PC smoke / Jetson replay target | `20260709_pc_alarm_service_skeleton_smoke_v3` | Project3 Jetson detector raw replay | 324 frames streamed by Project5 ReplayDetectorService | 5 | Project5 TemplateTextWorker rows=5 | Project5 StubVlmWorker rows=5 | 5 rows, event/alarm/per-event/stability schemas pass | service skeleton smoke, no monitor | `project5_service_skeleton_replay_not_verified` |
| PC smoke / Jetson replay target | `20260709_pc_alarm_service_worker_modes_smoke_v1` | Project3 Jetson detector raw replay | Project5 ReplayDetectorService | 3 | template worker rows=3 | stub worker rows=3 | 3 rows, four schemas pass | service worker mode smoke | `project5_service_worker_modes_not_verified` |
| PC smoke / Jetson replay target | `20260709_pc_alarm_service_call_budget_smoke_v1` | Project3 Jetson detector raw replay | Project5 ReplayDetectorService | 4 | `llama_cpp` mode with `--text-max-calls 0`, real calls=0 | `rkllm_multimodal` mode with `--vlm-max-calls 0`, real calls=0 | 4 rows, four schemas pass | call-budget fallback smoke | `project5_service_call_budget_not_verified` |
| RK3588 8GB / service VLM smoke | `20260709_rk3588_8gb_alarm_service_vlm_worker_smoke_v1` | `events_with_assets` via `--events-input` | detector skipped; consume Project5 event package | 3 | template fallback, `llm_call_count=0` | historical Qwen3-VL single-shot rows=3, bad=0, `vlm_call_count=3`, first total `21838 ms` | 3 rows, event/alarm/per-event/stability schemas pass | historical single-shot service smoke; after Project5 fixed `<image>` prompt injection and Qwen3-VL token defaults, this run should be rerun before继续作为真实 VLM 证据引用 | `historical_project5_service_vlm_single_shot_route_smoke` |
| RK3588 8GB / service RKLLM smoke | `20260709_rk3588_8gb_alarm_service_rkllm_worker_smoke_v2` | Project3 RK3588 detector raw replay | Project5 ReplayDetectorService | 3 | real RKLLM rows=3, bad=0, contaminated=0, `llm_call_count=3`, first total `14583.9 ms`, first decode `11.3306 tok/s` | stub, `vlm_call_count=0` | 3 rows, event/alarm/per-event/stability schemas pass | service entry smoke, no resident LLM | `project5_service_real_rkllm_single_shot_smoke_pass` |
| RK3588 8GB / service combined smoke | `20260709_rk3588_8gb_alarm_service_rkllm_vlm_worker_smoke_v1` | `events_with_assets` via `--events-input` | detector skipped; consume Project5 event package | 3 | real RKLLM rows=3, bad=0, contaminated=0, `llm_call_count=3`, first total `12836.8 ms`, first decode `12.6287 tok/s` | historical Qwen3-VL rows=3, bad=0, `vlm_call_count=3`, first total `20644 ms` | 3 rows, event/alarm/per-event/stability schemas pass | combined service smoke, no resident detector/LLM/VLM；VLM 部分同样建议按修正后的 Project5 路径重跑 | `historical_project5_service_rkllm_vlm_single_shot_route_smoke` |
| RK3588 8GB / resident detector smoke | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` | Project5 local resident detector, `video_set_runtime_v1` playlist paced 600s | Project5 ResidentProcessDetectorService | 75 | template rows=75, `llm_call_count=0` | stub rows=75, `vlm_call_count=0` | 75 rows, four schema families pass | stability raw `window_sec=600.885`, `window_requirement_met=true`, `drop_count=0`, `event_queue_depth=3` | `resident_detector_smoke_pass_with_template_stub_workers` |
| RK3588 8GB / resident text smoke | `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1` | `--events-input` from Project5 validated events | detector skipped; consume Project5 event package | 3 | resident RKLLM rows=3, same `resident_server_pid=2046602`, `resident_model_load_count=1`, request index `1/2/3` | stub rows=3, `vlm_call_count=0` | 3 rows, four schema families pass | stability raw `window_sec=34.314`, `llm_call_count=3`, `drop_count=0`, `event_queue_depth=3` | `resident_text_worker_smoke_pass` |
| RK3588 8GB / asset worker smoke | `20260710_rk3588_8gb_alarm_service_asset_worker_smoke_v1` | `--events-input` from resident-detector events + `video_set_runtime_v1` playlist asset replay | detector skipped; consume Project5 event package | 3 | template fallback, `llm_call_count=0` | stub fallback, `vlm_call_count=0` | 3 rows, event/alarm/per-event/stability schemas pass; service log `asset_success=3`, `asset_keyframes=3`, `asset_rois=5` | stability raw `window_sec=0.232`, `event_queue_depth=3`, `drop_count=0`; this is video-playlist asset replay, not camera live asset service | `asset_worker_smoke_pass_video_playlist_only` |
| RK3588 8GB / camera frame-cache smoke | `20260710_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1` | Astra S OpenNI `2bc5/0402` via Project5 `resident_process` + detector-side `frame_cache_dir` | Project5 ResidentProcessDetectorService, 3553 frames in 121.302s | 0 | template not called | stub not called | no event/alarm/per-event rows generated | service log shows `asset_worker_info mode=frame_cache source_type=frame_cache_dir`; `service_stop frames=3553 events=0 alarms=0`; this proves camera + frame-cache pipeline started, but no candidate event was triggered. Recommended rerun entrypoint is `projects/05_alarm_system/scripts/service/run_rk3588_camera_frame_cache_smoke.sh`, not a hand-written long `--detector-command`. | `camera_frame_cache_input_pass_no_alarm_event` |
| RK3588 8GB / camera frame-cache smoke | `20260711_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1` | Astra S OpenNI `2bc5/0402` via Project5 wrapper `run_rk3588_camera_frame_cache_smoke.sh` | Project5 ResidentProcessDetectorService | 3 | template not called, `llm_call_count=0` | stub not called, `vlm_call_count=0` | 3 rows, event/alarm/per-event/stability schemas pass | `window_sec=21.501`; this run intentionally stops early because the wrapper fixes `MAX_EVENTS=3`, so it is an asset smoke rather than a sustained stability run | `camera_frame_cache_asset_smoke_pass` |
| RK3588 8GB / resident VLM smoke | `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` | `events_with_assets` via `--events-input` | detector skipped; consume Project5 event package | 3 | template fallback, `llm_call_count=0` | resident Qwen3-VL rows=3, bad=0, same `resident_server_pid=2436647`, `resident_model_load_count=1`, request index `1/2/3` | 3 rows, four schema families pass | stability raw `window_sec=34.073`, `vlm_call_count=3`, `event_queue_depth=3`, `drop_count=0`; proves Project5 local resident VLM server handles multiple events after one load | `resident_vlm_worker_smoke_pass` |
| RK3588 8GB / resident service concurrency smoke | `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` | Project5 local resident detector + detector-side `frame_cache_dir` + `video_set_runtime_v1` paced 600s | Project5 ResidentProcessDetectorService + resident text worker + resident VLM worker | 75 | resident RKLLM rows=75, pass rows=2, same `resident_server_pid=2878366`, `resident_model_load_count=1`, request index `1/2` | resident Qwen3-VL rows=75, pass rows=2, same `resident_server_pid=2878497`, `resident_model_load_count=1`, request index `1/2` | 75 rows, four schema families pass | stability raw `window_sec=603.714`, `requested_window_sec=600.0`, `window_requirement_met=true`, `detection_fps=29.89495`, `event_queue_depth=19`, `drop_count=0`, `fallback_count=73`, monitor rows=561，收敛参数为 `FRAME_CACHE_CAPACITY=512`、`SERVICE_QUEUE_CAPACITY=32`、`DETECTOR_QUEUE_CAPACITY=16`、`CLEAN_FRAME_CACHE_ON_EXIT=1` | `resident_service_smoke_pass_with_resident_text_vlm_workers` |
| PC / B 方案 resident-process 入口 smoke | `20260709_pc_alarm_service_resident_process_smoke_v3` | Project5 local fake detector process | Project5 ResidentProcessDetectorService | 3 | template fallback, `llm_call_count=0` | stub, `vlm_call_count=0` | 3 rows, event/alarm/per-event/stability schemas pass, `status=pass` | 证明 service 可启动/停止 detector 进程并 tail JSONL；不是板端真实 detector | `resident_process_entry_smoke_pass` |

证据边界：`pass` 和 `smoke_pass` 均限定在上表对应链路。当前可以声明 Jetson resident detector smoke 已通过、Jetson resident text worker 已证明一次加载多请求复用、Jetson standalone resident VLM smoke 已通过、Jetson 单板 P7 已拿到有效时间窗但仍未通过、RK3588 Qwen3-VL ROI single-shot runtime 路线已跑通、Project5 B 方案 resident-process 入口层已跑通、RK3588 resident detector + queue + AlarmSink 10 分钟 smoke 已通过、RK3588 Project5 resident text worker 已证明一次加载多请求复用、RK3588 Project5 resident VLM worker 已证明一次加载多请求复用、RK3588 单板 `resident detector + resident text/VLM` 同窗 10 分钟 smoke 已通过、RK3588 单板 30 分钟 `resident_service_required` 已通过，以及 RK3588 单板 2 小时 `resident_service_target` 已拿到有效窗口证据；不能声明 SmolVLM2 视频理解能力、Jetson 单板 `resident_service_smoke` / `resident_service_required` 已通过，或 Jetson/RK3588 双板 P9 target 已完成。

按最新板端结果，这里的 Jetson 口径应明确区分为三层：1) standalone resident VLM 已通过 `v4`；2) Jetson P7 已通过 `v8` 进入有效时间窗；3) 当前未通过的具体原因是 resident multimodal request path，表现为真实图片请求的断连与超时，而不是“没有代码”或“服务起不来”。

对 RK3588 camera/OpenNI/RTSP 资产 smoke，当前统一建议使用 `projects/05_alarm_system/scripts/service/run_rk3588_camera_frame_cache_smoke.sh`。这个脚本会安全拼接 Project5 本地 detector 命令、清理旧 frame cache/log/JSONL，并固定使用 `template` 文本和 `stub` VLM，因此它验证的是 detector 常驻 + frame-cache 资产路径，而不是“所有模型常驻”。

## RK3588 下一阶段实现状态

围绕“先做完 RK3588 再做 Jetson”，当前 RK3588 已经完成和未完成的边界如下：

| 模块 | 当前代码状态 | 当前证据状态 | 结论 |
|---|---|---|---|
| Project5 local RKNN detector | 已实现并编译 | 已完成 10 分钟真实 resident smoke | 已通过 P3 |
| EventQueue + AlarmSink | 已实现 | 已在 P3 smoke 中持续写出 event/alarm/per-event/stability raw | 已通过 P3 |
| Project5 local RKLLM single-turn runner | 已补入 Project5 本地源码与构建脚本 | 已通过 `20260709_rk3588_8gb_alarm_service_rkllm_worker_smoke_v2` 完成 Project5 service single-shot smoke | 作为接口/回退与对照路径保留，不再是当前主缺口 |
| Project5 local RKLLM resident text server | 已补入 Project5 本地源码、构建脚本、service client 与 `--text-mode rkllm_resident` 接入 | 已通过 `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1`，同一 pid、`model_load_count=1`、请求序号递增 | 已通过 RK3588 P6-text smoke |
| Project5 local AssetWorker | 已实现 `asset_worker.py`，支持显式 `video_file`/`video_playlist` 路径和 `frame_cache_dir` | 已通过 `20260710_rk3588_8gb_alarm_service_asset_worker_smoke_v1/v2`；`20260711_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1` 已完成带真实事件的 camera frame-cache asset smoke | 已完成视频回放与 camera frame-cache 资产 smoke；后续缺口转为 resident/warm VLM worker |
| Project5 local resident/warm VLM worker | 已补入 Project5 本地源码、client、build 脚本和 service mode | 已通过 `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1`，同一 pid、`model_load_count=1`、请求序号递增、四类 schema pass | 已通过 RK3588 P6-vlm smoke，并已在 `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3`、`20260713_rk3588_8gb_alarm_service_resident_required_v2`、`20260713_rk3588_8gb_alarm_service_resident_target_v2` 进入同窗并发 smoke/required/target |
| Project5 local resident integrated service | 已具备 Project5 本地 resident detector、`frame_cache_dir`、resident text worker、resident VLM worker 与统一 AlarmSink/Benchmark/Monitor 接入 | 已通过 `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3`，`window_sec=603.714`、`detection_fps=29.89495`、`llm_call_count=2`、`vlm_call_count=2`、`event_queue_depth=19`、`drop_count=0`，文本/图文 worker 均保持同一 pid 与 `model_load_count=1`；随后 `20260713_rk3588_8gb_alarm_service_resident_required_v2` 与 `20260713_rk3588_8gb_alarm_service_resident_target_v2` 又补齐了单板 required/target | RK3588 单板 P7/P8/P9 已完成；下一缺口收敛为 Jetson P6-VLM、Jetson 单板 P7/P8 与双板 P9 |

## 常驻服务目标与当前缺口

如果项目五最终目标是“在线边缘告警解释系统”，系统必须至少满足下面服务化边界。当前实测主要是分阶段验证和后处理闭环，尚未完全达到最终系统形态。

| 模块 | 最终系统要求 | 当前证据 | 当前结论 |
|---|---|---|---|
| DetectorService | YOLO 检测模型常驻运行，持续读取视频/摄像头，不能被 LLM/VLM 阻塞 | 项目三 Jetson/RK3588 已有实时 30min detector raw；项目五已实现 `ResidentProcessDetectorService`、本地 detector 源码和双板 build 脚本，并通过 PC 本地 fake detector smoke；RK3588 本地 RKNN runner 已编译并完成 `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` 与 `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` / `20260713_rk3588_8gb_alarm_service_resident_required_v2` / `20260713_rk3588_8gb_alarm_service_resident_target_v2`；Jetson 本地 TensorRT runner 已在 `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` 完成 10 分钟窗口 | Jetson/RK3588 的 Project5 resident detector 均已有板端证据；RK3588 单板 resident service 已完成 smoke/required/target，下一步主缺口转向 Jetson resident VLM 与 Jetson 单板 P7/P8 |
| DetectionEventQueue | 检测线程只写事件队列，队列有容量、冷却、丢弃策略和日志 | event package 中已有 `queue_depth_at_trigger`、规则冷却和 drop 字段；真实服务队列未独立压测 | 数据结构具备，服务化队列验收未完成 |
| TextWorker | 文本 LLM 低频异步消费事件；理想状态是 resident worker 或可解释的 warm pool | Jetson 真实 Qwen3 text rows=10；RK3588 真实 RKLLM rows=3/2；Project5 已新增本地 `rkllm_resident_text_server`、Jetson `llama_cpp_resident` client、build/service 接入和 Jetson P6 smoke wrapper，并在 `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1`、`20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` / `20260713_rk3588_8gb_alarm_service_resident_required_v2` / `20260713_rk3588_8gb_alarm_service_resident_target_v2`、`20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` 以及 `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` 中给出同一 pid、`model_load_count=1` 证据 | RK3588 resident text worker 与同窗 smoke/required/target 已有实测；Jetson resident text worker 已完成最小复用 smoke，且 Route B realtime 已证明 `detector + resident text` 运行时链路成立；但 `20260714_...detector_text_resident_smoke_v1` 的第 2 条真实解释把 `vehicle_presence/car` 错写成“未佩戴安全帽”，因此 Jetson text 当前只能声明 runtime pass，不能直接声明业务语义 pass |
| VlmWorker | 图文 VLM 低频异步消费 ROI/关键帧；不能同步阻塞检测 | RK3588 真实 Qwen3-VL mt384 rows=3，Alarm JSON/per-event schema pass；`20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` 与 `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` 又证明同一 resident VLM pid 连续处理多个事件、`model_load_count=1`；Jetson 侧已补入 Project5 本地 multimodal `llama-server` client、`--vlm-mode llama_cpp_multimodal_resident` 和 `run_jetson_p6_resident_vlm_smoke.sh`，并已在 `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 拿到 standalone resident VLM 通过证据；`20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` 与 `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 又进一步证明：即便把 resident text 从链路里拿掉，Jetson resident VLM 的真实图片请求仍会 timeout | RK3588 resident VLM worker 与同窗 smoke 已有实测；Jetson resident VLM standalone 已通过，但 Route A 和 Route B async enrichment 都仍卡在 request path，说明当前主阻塞点已经收口为 Jetson multimodal request path 本身 |
| AlarmSink | 持续输出 schema-safe Alarm JSON，并记录 fallback/status/benchmark | Jetson/RK3588 多个 run 已 schema pass；Project5 service 已可持续写 events/LLM/VLM/alarms/per-event/stability raw；resident-process PC smoke 四类 schema pass | JSON 闭环已验证；真实板端常驻服务输出未完成 |
| CodeBoundary | 项目五最终服务代码独立，前序项目只作为 artifact/reference | 当前已有 Project5 本地 RKLLM text/VLM single-shot adapter 和 service skeleton，代码边界检查 `independent_runtime_pass` | 代码边界已过；最终系统仍需 05K resident service |

因此，当前项目五可以作为“端侧告警解释链路验证版”，且 B 方案 service 入口层已开始成形，但不能写成“Jetson/RK3588 完整在线常驻告警服务已完成”。下一阶段必须进入 `resident_service_concurrency` 验证：Project5 本地真实 DetectorService 常驻、事件队列异步、LLM/VLM worker 限频消费、监控检测 FPS delta、queue_depth、drop_count、model timeout 和资源峰值。

同时，下一阶段必须进入 `resident_service_required` 与 `resident_service_target` 收口：Project5 service 已经具备 `resident_process` detector 入口、Project5 本地 detector 源码/build 脚本、replay detector、events-input、有界队列、template/stub/real single-shot worker、视频回放 AssetWorker、detector-side frame cache 和 AlarmSink，代码边界已过；RK3588 resident detector 10 分钟 smoke、resident text smoke、resident VLM smoke、视频回放资产 smoke、camera frame-cache 资产 smoke、单板 30 分钟 required 和单板 2 小时 target 已完成，Jetson 本地 TensorRT runner、resident text 和 standalone resident VLM 也已完成；当前还要补的是 Jetson resident VLM request path 收口、Jetson 单板 P7/P8 通过判定，以及双板 P9 target，并继续保留 monitor 与 fallback 证据，才能写成最终系统完成。

## 走向最终系统的实施路线

项目五不允许把历史 smoke 直接拼成“最终系统完成”。从当前状态到双板最终验收的唯一顺序由 `projects/05_alarm_system/specs/05M_常驻告警系统实施路线图.md` 定义：P0/P1 模块与模型证据已完成，P2 项目五独立服务骨架已完成；RK3588 P3、P5、P6-text、P6-vlm、单板 P7 smoke 和单板 P8 required 已完成，Jetson P4、P6-text 和 P6-vlm 也已完成；当前实际进入 Jetson P7 request-path 收口、Jetson 单板 P8，以及双板 2 小时 target P9 阶段。

| 当前阶段 | 下一步 | 验证对象 | 通过后的唯一结论 |
|---|---|---|---|
| RK3588 P3 已完成 | Jetson P4 | Project5 local TensorRT detector、EventQueue、template/stub、AlarmSink、monitor | Jetson `resident_detector_smoke_pass_with_template_stub_workers` |
| RK3588 P3 / P5 / P6 / P7-smoke 已完成 | Jetson P4 | Project5 local TensorRT detector、EventQueue、template/stub、AlarmSink、monitor | Jetson `resident_detector_smoke_pass_with_template_stub_workers` |
| RK3588 单板 P7-smoke 已完成 | Jetson resident/warm worker | Jetson resident text、resident VLM standalone 与 Jetson P7 有效时间窗证据 | Jetson 单模块 smoke/resident evidence 已就位，下一步转向 P7/P8 通过判定 |
| Jetson P4 / P6 已完成、P7 valid window 已达成 | Jetson P7 / P8 收口 | Jetson resident multimodal request path、同窗 queue/resource 和 schema | `resident_service_smoke`，然后 `resident_service_required` |
| Jetson P8 后 | 双板 P9 | 双板 detector 与真实常驻 LLM/VLM 的隔离、队列、资源和 schema | `resident_service_target` |

05M 为每个阶段规定了实现改动、运行输入、必测 Benchmark、失败处理和禁止声明；05A/05B 只描述各板特有约束，05I/05J 只描述可复制执行命令，05K/05L 分别定义验收与代码边界。

项目四固定输入任务在项目五中的落点如下：

| 项目四任务 | 项目五落点 |
|---|---|
| 设备日志解释、部署错误解释 | `system_runtime` / `model_runtime` 故障告警解释 |
| 检测 JSON 摘要、告警原因和动作建议 | `text_explanation` 低频文本告警解释 |
| schema-safe JSON 输出 | `json_quality` 和 alarm JSON builder |
| bus/workstation/panel/ROI/abnormal 图片输入 | `visual_evidence` 低频 ROI/关键帧/面板复核 |
| 多帧视频输入 | 当前按项目四结论进入 `video_fallback`，不作为主线视频理解能力 |

## 主要功能

项目五系统至少包含下面功能：

| 功能 | 说明 | 验收证据 |
|---|---|---|
| 高频检测接入 | 继承项目三 YOLO11n pipeline，接入 frame-level detection JSONL | detector raw、runtime log、FPS/p95 |
| 事件触发 | 按类别、置信度、连续帧、冷却时间和可选 zone 生成候选事件 | event package、trigger_rule_id、trigger_reason |
| 证据资产生成 | 为事件保存关键帧、ROI 坐标、ROI 图片和短视频片段路径 | keyframe_path、roi_paths、roi_boxes、video_clip_path |
| 文本告警解释 | 用 Qwen3-1.7B 对检测事实、规则、日志和候选事件生成文本解释 | LLM raw、tokens/s、total_ms、fallback_status |
| 图文 ROI 复核 | Jetson/RK3588 上用项目四准入的 Qwen3-VL 对低频 ROI/关键帧做视觉问答或摘要 | VLM raw、ROI 输入、timeout/fallback；真实执行前必须有 `keyframe_path` 或 `roi_paths` |
| 系统和模型故障解释 | 对断流、队列堆积、模型 timeout/OOM、runtime 不支持做结构化解释 | failure log、fallback_status、troubleshooting |
| 结构化告警 JSON | 把检测事实、规则、模型解释、证据路径和资源指标写成统一 JSON | alarm JSON schema pass、fact conflict check |
| 失败降级 | LLM/VLM/视频/JSON 失败时仍输出 schema-safe 告警 | fallback_status、failure log、troubleshooting |
| Benchmark | 记录检测、事件、ROI、LLM/VLM、JSON、资源、稳定性指标 | per-event raw、processed summary、MLPerf-style Summary |

## 输入输出

| 类型 | 内容 |
|---|---|
| 输入视频 | 固定视频、摄像头或 RTSP；正式 run 必须固定 input_source_id |
| 检测输入 | 项目三 YOLO frame-level JSONL，包含 frame_id、timestamp、class_id、confidence、bbox |
| 配置输入 | 板卡配置、模型组合、事件规则、prompt、告警 schema |
| 中间输出 | event package、keyframe/ROI/clip 证据路径、LLM/VLM raw |
| 最终输出 | alarm JSON、per-event benchmark raw、stability raw、报告和问题库 |

一个合格的告警解释输出必须回答四个问题：

| 问题 | 对应字段 |
|---|---|
| 发生了什么候选事件或解释任务？ | `alarm_domain`、`alarm_type`、`trigger_rule_id`、`trigger_reason` |
| 证据来自哪里？ | `event_id`、`frame_id`、`detections`、`roi_boxes`、`keyframe_path` |
| 模型如何解释？ | `llm_explanation`、`vlm_summary`、`video_summary` |
| 系统状态是否可信？ | `json_schema_pass`、`json_fact_conflict`、`fallback_status`、`status` |

项目五是加分旗舰项目，但它必须建立在前置项目的证据上：

- 项目一提供 YOLO11n 多后端部署、模型产物、前后处理和 benchmark 口径。
- 项目三提供 C++ 实时视频流 pipeline、队列、断流恢复、稳定性和服务化口径。
- 项目四提供 LLM/VLM/视频理解模型在 8GB 开发板上的准入等级、输入限制、资源边界和降级策略。项目四已判定 RDK X5 不满足项目五主线准入，项目五后续只执行 Jetson 8GB 和 RK3588 8GB。

如果项目四某个模型组合没有准入结论，项目五不能把它写成可用系统能力，只能标记为 `blocked`、`not_executed` 或用 mock/stub 做接口联调。

## 总规范对齐

| 来源 | 要求 | 项目五落地方式 |
|---|---|---|
| `项目选题与作品集.md` | 边缘 LLM/VLM 告警解释系统 | 原计划三板；按项目四实测结论收敛为 Jetson、RK3588 双板主线，RDK X5 归档为失败路线 |
| `项目方案.md` | 项目五在项目四后做系统整合 | 以 `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` 为准入输入 |
| 项目一 | YOLO11n 部署基线 | 继承模型、前后处理、后端调用证据和检测 benchmark 口径 |
| 项目三 | C++ 实时视频流 pipeline | 继承 C++ pipeline、队列限流、断流恢复、稳定性监控和 runtime benchmark |
| 项目四 | LLM/VLM 独立验证 | 继承 A/B/C/D 准入等级，项目五只做系统并行和端到端复测 |
| `问题库.md` | 故障复盘机制 | 所有系统整合问题写入 `projects/05_alarm_system/reports/troubleshooting.md` |
| `MLPerf风格Benchmark规范.md` | 统一 benchmark 与报告 | `alarm_system_benchmark.md`、`llm_vlm_benchmark.md`、`video_understanding_benchmark.md` 必须包含 MLPerf-style Summary |
| 稳定性监控横向能力 | 项目五必须执行稳定性实验 | `05F_稳定性监控规范.md`、`logs/monitor/05_alarm_system/`、`stability_report.md` |

## 执行自由度与硬性证据约束

本项目的 specs 是执行参考书，不是唯一脚本。执行者可以替换服务框架、队列实现、模型 runner、监控工具、告警输出格式和部署方式，但不能替换项目目标。

硬性约束：

- 高频 YOLO 检测链路不能被 LLM/VLM 阻塞。
- 每个告警必须有唯一 `event_id`，并能追溯到帧、检测结果、ROI、视频片段、模型输出、日志和 raw result。
- 项目四 A/B/C/D 准入等级必须被显式引用；项目五不能把 `B_low_frequency` 或 `C_offline` 模型写成实时主线。
- 每块主线板必须记录环境基线、模型组合、后端 runtime、配置、命令、raw result、runtime 日志、monitor 日志和问题记录。
- `target=pc` 只能用于脚本调试、CPU baseline、接口联调或模型格式预检；PC run 不能作为 Jetson 或 RK3588 的系统能力结论，也不能被选为双板正式 selected run。
- 端到端 benchmark 必须拆分检测、事件触发、抽帧/ROI、VLM、视频理解、LLM、JSON schema 校验耗时。
- 稳定性实验必须真实执行；不能只在报告中写“计划执行”。
- 失败、超时、OOM、swap 过高、温控降频、断流、JSON 不合格、模型输出与检测事实冲突都必须进入问题库。

执行过程可以发挥，但最终证据链必须完整。

## 项目边界

包含：

- Jetson 和 RK3588 双板告警解释系统的模型组合和部署路线。
- 项目三 YOLO11n 实时检测结果接入。
- 事件触发、抽帧、ROI 裁剪、短视频片段截取。
- 图文 VLM 低频问答。
- 图文 VLM 低频 ROI/关键帧解释。
- Qwen3-1.7B 文本告警解释；Gemma 4/Gemma 3n 只在项目四证据允许时作为历史对照或离线能力。
- 结构化告警 JSON schema、校验和失败回退。
- 端到端 benchmark、稳定性监控、异常注入、降级策略。

不包含：

- LLM/VLM 独立可行性验证，属于项目四。
- YOLO11n 单模型导出、转换和单图 benchmark，属于项目一。
- C++ 视频 pipeline 基础工程能力验证，属于项目三。
- 量化策略和精度恢复，属于项目二。
- 模型压缩训练，属于项目六。

## 继承规则

### 项目一继承

项目五的检测链路必须优先继承项目一产物：

| 继承项 | 项目五用途 |
|---|---|
| `models/yolo11n/` 下的 ONNX / TensorRT / RKNN / BPU 产物 | 板端检测后端 |
| `projects/01_vision_deploy/configs/preprocess/` | 保持 YOLO 输入预处理一致 |
| `projects/01_vision_deploy/configs/postprocess/` | 保持检测框和 NMS 口径一致 |
| `projects/01_vision_deploy/reports/accuracy_alignment.md` | 说明检测结果可信边界 |
| `projects/01_vision_deploy/reports/benchmark.md` | 检测基线指标来源 |
| `docs/standards/模型变更质量对齐规范.md` | 检测模型、LLM/VLM、prompt、事件规则或告警 JSON 变化后的质量对齐状态规则 |

### 项目三继承

项目五的高频检测服务必须优先继承项目三 pipeline：

| 继承项 | 项目五用途 |
|---|---|
| `projects/03_video_pipeline/reports/video_pipeline.md` | 视频流架构和线程模型 |
| `projects/03_video_pipeline/reports/runtime_benchmark.md` | 检测链路 FPS、p95/p99、分阶段耗时 |
| `projects/03_video_pipeline/reports/stability_report.md` | 检测链路稳定性基线 |
| `projects/03_video_pipeline/reports/failure_and_fallback.md` | 断流、队列堆积、服务恢复策略 |
| `benchmark/raw/03_video_pipeline/<board>/` | 检测 pipeline 原始指标 |

如果项目五重新实现检测输入层，必须说明为什么不直接复用项目三，并证明指标和稳定性不倒退。

### 项目四继承

项目五的 LLM/VLM/视频理解模型必须继承项目四准入结果：

| 继承项 | 项目五用途 |
|---|---|
| `projects/04_llm_vlm_independent/reports/llm_vlm_model_matrix.md` | 三板模型可行性矩阵；项目五只继承 Jetson/RK3588 主线，RDK X5 失败路线归档 |
| `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` | 项目五模型组合准入依据 |
| `projects/04_llm_vlm_independent/reports/model_failure_and_fallback.md` | 模型失败和降级策略 |
| `projects/04_llm_vlm_independent/reports/*_benchmark.md` | 单模型性能、资源和质量证据 |
| `benchmark/raw/04_llm_vlm_independent/<board>/` | LLM/VLM 原始指标 |

准入等级在项目五中的含义：

| 项目四等级 | 项目五使用方式 |
|---|---|
| `A_mainline` | 可以进入项目五默认在线或低频链路，但仍需做系统并行复测 |
| `B_low_frequency` | 只能事件触发、人工触发、异步调用或排队调用 |
| `C_offline` | 只能做离线分析、报告展示或非实时补充，不进入在线链路 |
| `D_not_used` | 不接入项目五，只保留问题和替代方案 |
| `not_executed` / 空白 | 项目五对应能力标记为 `blocked` 或使用 mock/stub 联调 |

## 目录结构

项目五使用项目本地目录保存代码、配置、运行记录和报告；共享输入、模型、benchmark 和日志放在仓库全局目录。

```text
edge-inference-deploy-lab/
  projects/
    05_alarm_system/
      05_三板边缘LLM_VLM告警解释系统.md
      specs/
        00_environment_baseline_template.md
        00_run_record_template.md
        05A_Jetson_告警解释系统规范.md
        05B_RK3588_告警解释系统规范.md
        05D_事件触发与抽帧ROI规范.md
        05E_结构化告警JSON规范.md
        05F_稳定性监控规范.md
        05G_统一告警系统Benchmark与报告规范.md
        05H_告警业务语义与事件规则规范.md
        05I_Jetson_正式执行流程.md
      src/
        detector/
        event_trigger/
        frame_sampler/
        vlm_client/
        llm_client/
        alarm_output/
        service/
      scripts/
        run_demo/
        benchmark/
        monitor/
        report/
        service/
      configs/
        boards/
        models/
          model_combo_schema.yaml
        inputs/
          video_sources.yaml
        event_rules/
        alarm_schema/
          alarm_event_schema.json
      runs/
        <run_id>/
          run.md
          outputs/
          config_snapshot/
          event_samples/
          alarm_samples/
          notes.md
      reports/
        input_sources.md
        board_matrix.md
        yolo11n_realtime_benchmark.md
        llm_vlm_benchmark.md
        video_understanding_benchmark.md
        event_pipeline.md
        stability_report.md
        failure_and_fallback.md
        alarm_system_benchmark.md
        troubleshooting.md
  data/
    videos/
    images/
    prompts/
    validation/
  models/
    yolo11n/
    llm_vlm/
  benchmark/
    raw/
      05_alarm_system/
        jetson_8gb/
        rk3588_8gb/
    processed/
      05_alarm_system/
    reports/
      05_alarm_system/
    schemas/
      alarm_system_raw_schema.json
      alarm_system_stability_schema.json
      alarm_event_package_schema.json
  logs/
    benchmark/05_alarm_system/
    runtime/05_alarm_system/
    monitor/05_alarm_system/
    failures/05_alarm_system/
```

路径使用原则：

- 项目五配置只放在 `projects/05_alarm_system/configs/`。
- 项目五运行记录只放在 `projects/05_alarm_system/runs/<run_id>/run.md`。
- 项目五人工报告只放在 `projects/05_alarm_system/reports/`。
- 原始 benchmark 只写入 `benchmark/raw/05_alarm_system/<board>/`，不手工修改。
- 日志按类别写入 `logs/<category>/05_alarm_system/<board>/`。

代码边界使用原则：

- 项目五最终服务入口必须放在 `projects/05_alarm_system/scripts/service/` 或 `projects/05_alarm_system/src/service/`。
- 项目五可以读取 `benchmark/raw/03_video_pipeline/` 作为 replay 输入，但该结果只能支持后处理链路验证，不能替代项目五 DetectorService。
- 项目五可以使用 `models/llm_vlm/` 和项目四准入报告，但不能把项目四 shell wrapper 作为最终 resident worker。
- 若 Project5 脚本仍直接引用 `projects/03_video_pipeline` 或 `projects/04_llm_vlm_independent`，必须在报告中写 `code_boundary_status=artifact_replay_pass` 或 `legacy_adapter_smoke`。

## 模型组合基线

下表是项目五的初始计划，不是最终结论。最终组合必须以项目四 `project5_integration_decision.md` 为准。

| 开发板 | 高频检测 | 文本解释主线 | 图文 VLM | 视频理解 | 项目五定位 |
|---|---|---|---|---|---|
| Jetson 8GB | YOLO11n + TensorRT INT8 | Qwen3-1.7B GGUF Q4_K_M，`B_low_frequency`，异步事件触发 | Qwen3-VL-2B Q4_K_M + mmproj F16，`B_low_frequency`，ROI/关键帧低频异步 | 当前 SmolVLM2 多帧视频 `D_not_used`，改用检测/抽帧摘要 | 检测 + 文本解释 + 低频 ROI VLM 主展示平台 |
| RK3588 8GB | YOLO11n + RKNN | Qwen3-1.7B RKLLM，`B_low_frequency`，异步事件触发 | Qwen3-VL RKNN vision + RKLLM decoder，`B_low_frequency`，低频 ROI/关键帧 | 当前 SmolVLM2 视频 `D_not_used`，改用检测/抽帧摘要 | 检测 + 文本解释 + 低频 ROI VLM |

RDK X5 8GB 已按项目四失败结论从项目五主线删除，不再进入本项目后续实验表、benchmark 横向对比和稳定性验收。

## 系统链路

推荐运行链路：

```text
VideoSource
-> DetectorService
-> DetectionEventQueue
-> EventTrigger
-> EventPackage
   - event_id
   - frame_id / timestamp
   - detections
   - keyframe_path
   - roi_paths
   - video_clip_path
   - source_metrics
-> ModelRouter
   - text_llm
   - image_vlm
   - video_vlm
-> AlarmJsonBuilder
-> SchemaValidator
-> AlarmSink
-> BenchmarkRecorder
```

关键原则：

- `DetectorService` 高频运行。
- `ModelRouter` 低频或异步运行。
- VLM 和视频理解不能反向阻塞检测线程。
- 事件队列必须有容量、超时、丢弃策略和日志。
- 模型调用必须有超时和 fallback。
- 告警 JSON 必须保留原始检测事实，LLM 不能覆盖 YOLO 检测结果。

## 输入资产

| 输入 | 路径或来源 | 要求 |
|---|---|---|
| 视频输入 | `data/videos/` 或摄像头/RTSP | 固定视频用于可复现 benchmark，摄像头用于实机演示 |
| 输入源 manifest | `projects/05_alarm_system/configs/inputs/video_sources.yaml` | 固定 `input_source_id`、fps、分辨率、hash、可访问性和时间戳来源 |
| 检测模型 | `models/yolo11n/` | 继承项目一和项目三验证过的模型产物 |
| LLM/VLM 模型 | `models/llm_vlm/` | 继承项目四准入结论 |
| Prompt 模板 | `data/prompts/` 或 `projects/05_alarm_system/configs/models/` | 固定版本、记录 hash |
| 模型组合 schema | `projects/05_alarm_system/configs/models/model_combo_schema.yaml` | 固定 detector、LLM、VLM、video、fallback 必填字段 |
| 事件规则 | `projects/05_alarm_system/configs/event_rules/` | 类别、置信度、ROI、持续帧数、冷却时间 |
| 板卡配置 | `projects/05_alarm_system/configs/boards/` | 模型组合、队列、超时、监控、电源模式 |
| JSON schema | `projects/05_alarm_system/configs/alarm_schema/` | 告警结构化输出校验 |

## 输出资产

| 输出 | 路径 | 用途 |
|---|---|---|
| 事件包 metadata | `benchmark/raw/05_alarm_system/<board>/events/` | 记录 event_id、帧、检测、ROI、视频片段 |
| 告警 JSON | `benchmark/raw/05_alarm_system/<board>/alarms/` | 结构化告警原始结果 |
| raw benchmark | `benchmark/raw/05_alarm_system/<board>/` | 端到端和分模块指标 |
| processed benchmark | `benchmark/processed/05_alarm_system/` | 聚合表、schema 校验、横向对比 |
| 板卡矩阵 | `projects/05_alarm_system/reports/board_matrix.md` | Jetson/RK3588 模型组合和准入状态 |
| 事件链路报告 | `projects/05_alarm_system/reports/event_pipeline.md` | 事件触发、抽帧、ROI、队列策略 |
| 系统 benchmark | `projects/05_alarm_system/reports/alarm_system_benchmark.md` | 端到端延迟、质量、资源、可复现 |
| 稳定性报告 | `projects/05_alarm_system/reports/stability_report.md` | 30 分钟、2 小时、异常注入 |
| 降级报告 | `projects/05_alarm_system/reports/failure_and_fallback.md` | 超时、OOM、断流、JSON 不合格等处理 |
| 问题库 | `projects/05_alarm_system/reports/troubleshooting.md` | 系统整合问题复盘 |

## 执行入口

| spec | 作用 |
|---|---|
| `projects/05_alarm_system/specs/00_environment_baseline_template.md` | 项目五环境基线模板，覆盖检测 runtime、LLM/VLM runtime、服务环境、输入源和监控工具 |
| `projects/05_alarm_system/specs/00_run_record_template.md` | 项目五目录式 run 记录模板，覆盖前置证据、模型组合、输入源、event package、alarm JSON、raw、日志和稳定性 |
| `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` | Jetson 主线：YOLO + Qwen3-1.7B 文本 LLM + Qwen3-VL 低频 ROI；视频理解按项目四结论禁用或专项复测 |
| `projects/05_alarm_system/specs/05B_RK3588_告警解释系统规范.md` | RK3588 主线：YOLO + Qwen3-1.7B 文本解释，VLM/视频按项目四等级降级 |
| `projects/05_alarm_system/specs/05D_事件触发与抽帧ROI规范.md` | event_id、事件包、ROI、短视频片段和队列策略 |
| `projects/05_alarm_system/specs/05E_结构化告警JSON规范.md` | 告警 JSON 字段、schema、质量校验和 fallback |
| `projects/05_alarm_system/specs/05F_稳定性监控规范.md` | 30 分钟必测、2 小时目标、异常注入和恢复策略 |
| `projects/05_alarm_system/specs/05G_统一告警系统Benchmark与报告规范.md` | schema 校验、最新有效 run、excluded runs、processed result 和统一报告生成 |
| `projects/05_alarm_system/specs/05H_告警业务语义与事件规则规范.md` | 告警类型、候选事件、禁用业务告警、事件规则和质量状态边界 |
| `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md` | Jetson 从项目三 detector raw 到 event package、真实/模板 LLM、alarm JSON、per-event raw 和回填报告的可执行命令序列 |
| `projects/05_alarm_system/specs/05J_RK3588_正式执行流程.md` | RK3588 从项目三 detector raw 到真实 RKLLM、真实 Qwen3-VL ROI smoke、Alarm JSON、per-event raw 和回填报告的可执行命令序列 |
| `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` | 最终在线系统目标：DetectorService 常驻、事件队列异步、LLM/VLM worker 限频消费、AlarmSink 持续输出和并发稳定性验收 |
| `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md` | 项目五与项目三/四的代码边界：允许继承 artifact 和证据，禁止最终服务直接耦合前序项目脚本 |
| `projects/05_alarm_system/specs/05M_常驻告警系统实施路线图.md` | 从既有模块 smoke 到双板最终常驻服务的阶段顺序、实现任务、证据门槛、失败回退和可声明结论 |

## 阶段拆分

| 阶段 | 目标 | 输入 | 输出 | 验收 |
|---|---|---|---|---|
| 0. 准入冻结 | 确定项目五模型组合 | 项目四准入报告 | `board_matrix.md` 初版 | 每个模型有 A/B/C/D 或 blocked |
| 1. 检测接入 | 接入项目三高频检测 | 视频源、YOLO pipeline | 检测 JSON、frame_id | FPS 和 p95 不低于项目三可解释范围 |
| 2. 事件包 | 抽帧、ROI、短视频片段 | 检测 JSON | event package | event_id 可追溯，ROI 坐标正确 |
| 3. 文本解释 | 接入文本 LLM | 检测 JSON、日志、prompt | 文本解释 | first token、tokens/s、质量可记录 |
| 4. 图文 VLM | 低频解释关键帧/ROI | event package | VLM summary | 不阻塞检测，超时可回退 |
| 5. 视频理解/替代摘要 | 按准入等级处理短片段；Jetson 当前默认禁用 SmolVLM2 | 事件片段、检测结果、ROI 摘要 | video summary 或 fallback 状态 | 未准入时必须写 `disabled_by_project4_decision` |
| 6. 告警 JSON | 结构化输出 | 检测、VLM、LLM、metrics | alarm JSON | schema 合格，事实不被 LLM 覆盖 |
| 7. 双板 benchmark | 横向比较 | Jetson/RK3588 链路 | benchmark 报告 | 指标完整，可追溯 |
| 8. 后处理稳定性 | 证明 detector realtime run 后，项目五后处理链路可闭环 | 固定输入源、Project3 raw | stability/fallback 报告 | 30 分钟通过只能说明 post-detector chain |
| 9. 常驻服务并发 | 证明在线服务形态达成 | 常驻 DetectorService、EventQueue、LLM/VLM worker | resident service raw、service log、monitor | 10 分钟 smoke、30 分钟 required、2 小时 target；按 05K 验收 |
| 10. 独立代码库验收 | 证明 Project5 服务代码独立，不直接耦合项目三/四脚本 | Project5 service 入口、本地 adapter、本地队列和 AlarmSink | code boundary check、service run、raw/log | 按 05L 验收；最终完成必须 `independent_runtime_pass` |

## Benchmark 指标

| 类别 | 指标 |
|---|---|
| 检测 | YOLO FPS、p50/p90/p95/p99、分阶段耗时、丢帧率、队列长度 |
| 事件 | trigger latency、event queue wait、ROI crop latency、video clip latency、event drop count |
| 告警语义 | candidate_event_count、event_rate_per_min、按 `alarm_domain`/`alarm_type` 聚合、candidate_to_verified_rate |
| VLM | image preprocess、first token、prefill、tokens/s、total time、timeout rate、quality pass rate |
| 视频理解 | clip duration、sampled frames、decode time、video preprocess、first token、tokens/s、summary quality |
| LLM | first token、prefill、decode tokens/s、total generation time、prompt/output tokens、JSON 修复次数 |
| 告警 JSON | schema pass rate、required field missing count、fact conflict count、event trace pass rate、fallback status |
| 资源 | CPU/GPU/NPU/BPU 利用率、内存峰值、swap used、温度、功耗或电源模式 |
| 稳定性 | sustained 时长、事件数、异常恢复次数、重启次数、内存增长、温控降频 |
| 可复现 | environment_baseline_id、run_id、config hash、model hash、raw result、log path |

## Raw / Processed Result 口径

项目五 raw result 分成两类，不混用：

| schema | 粒度 | 用途 |
|---|---|---|
| `benchmark/schemas/alarm_system_raw_schema.json` | `per_event` | 一个 `event_id` 对应的一次告警生成记录 |
| `benchmark/schemas/alarm_system_stability_schema.json` | `time_window` | 稳定性测试中的一个时间窗口采样 |

event package 必须符合 `benchmark/schemas/alarm_event_package_schema.json`。告警 JSON 必须符合 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json`。

per-event raw JSON/CSV 至少包含：

```text
run_id
timestamp
schema_version
project
measurement_granularity
board
target
environment_baseline_id
event_id
alarm_domain
alarm_type
event_stage
input_source_id
frame_id
model_combo_id
detector_backend
detector_artifact_sha256
detector_precision
llm_model
vlm_model
video_model
project4_decision_refs
detection_latency_ms
event_trigger_latency_ms
roi_crop_latency_ms
video_clip_latency_ms
vlm_total_ms
video_understanding_total_ms
llm_first_token_ms
llm_decode_tokens_per_s
llm_total_ms
json_schema_pass
json_fact_conflict
json_repair_count
end_to_end_alarm_ms
memory_peak_mb
swap_used_mb
temperature_max_c
power_w
power_mode
cpu_gpu_npu_bpu_utilization
queue_depth_max
drop_count
fallback_status
status
raw_event_path
alarm_json_path
runtime_log_path
monitor_log_path
failure_log_path
related_troubleshooting_id
```

`p50/p90/p95/p99`、schema pass rate、平均 FPS、总 event_count、总 alarm_count 等进入 `benchmark/processed/05_alarm_system/`，不写入 per-event raw 行。

## 告警 JSON 最小字段

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
```

LLM/VLM 输出只能补充解释，不能删除或改写原始检测事实。事实冲突必须标记 `json_fact_conflict=true`，并进入问题库。

## 模型变更质量对齐

项目五的质量对齐不是单一 mAP 指标，而是端到端告警任务质量。下面变化会触发质量对齐：

- 检测模型、检测后端、前处理、后处理、NMS、类别映射或输入尺寸变化。
- LLM/VLM/视频理解模型、runtime、量化格式、tokenizer/processor、prompt template、generation 参数变化。
- 事件触发规则、ROI 裁剪、短视频截取、模型路由、fallback 策略或告警 JSON schema 变化。

固定输入对齐至少检查 event package、ROI 坐标、检测事实、LLM/VLM 输出摘要、告警 JSON schema 和 `json_fact_conflict`。任务级质量对齐至少统计固定事件集上的 `json_schema_pass_rate`、`event_trace_pass_rate`、`fact_conflict_rate`、fallback success rate 和端到端告警成功率。

只完成端到端 smoke、性能 benchmark 或少量固定事件对齐时，不能把系统质量状态写成 `pass`；缺少任务级固定事件集评估时只能写 `not_verified`。只有检测质量、结构化 JSON、事实一致性和 fallback 行为均满足阈值，才能写 `pass`。

## 稳定性实验

项目五必须执行稳定性实验：

- 10 分钟 smoke：用于验证链路启动、事件包和 JSON 输出。
- 30 分钟必测：作为项目五稳定性最低门槛。
- 2 小时目标：作为作品集验收目标。
- 可选 8 小时压力：用于展示生产化能力。

异常注入至少覆盖：

- 摄像头/视频源断流。
- 事件突增导致队列堆积。
- VLM 超时。
- LLM 超时或输出非 JSON。
- 内存压力或 swap 增长。
- 温度升高或功耗/电源模式变化。

## 问题库触发条件

下面情况必须写入 `projects/05_alarm_system/reports/troubleshooting.md`：

- 项目四准入证据缺失，但项目五需要该模型。
- 检测模型、LLM/VLM、prompt、事件规则或告警 schema 变化后，缺少固定输入对齐或任务级告警质量评估。
- VLM/视频理解阻塞高频检测。
- LLM 超时、输出非 JSON、输出与检测事实冲突。
- event_id 无法追溯到帧或 raw result。
- ROI 坐标错位、关键帧丢失、视频片段截取失败。
- 事件队列堆积、丢弃策略不清、告警延迟不可控。
- 摄像头断流、服务崩溃、重启失败。
- 内存不足、swap 过高、温控降频、功耗或电源模式不明确。
- benchmark 字段缺失或报告结论无法追溯。

## 最终验收标准

- Jetson 至少完成一条完整链路：YOLO 检测、事件包、文本解释、结构化告警 JSON；图文 VLM 和视频理解按项目四准入等级启用。
- RK3588 至少完成 YOLO11n + Qwen3-1.7B 文本解释主线；VLM/视频理解不能被写成实时能力，除非项目四和项目五复测都支持。
- Jetson/RK3588 都有 `board_matrix.md` 中的模型组合、准入等级和证据路径。
- 正式事件规则符合 05H，不使用 `generic_object_event`，且候选告警按 `alarm_domain=visual_detection` 下的 `person_presence`、`vehicle_presence`、`multi_object_scene` 聚合；解释、故障和降级任务按对应 `alarm_domain` 聚合。
- 每个告警 JSON 能追溯到 event package、模型输出、日志和 raw result。
- 模型组合、prompt、事件规则、ROI、fallback 或告警 schema 变化后的质量结论必须同时包含固定输入对齐和固定事件集任务级质量评估；只完成 smoke 或性能 benchmark 时状态只能 `not_verified`。
- `alarm_system_benchmark.md` 包含 MLPerf-style Summary 和横向总表。
- `stability_report.md` 至少覆盖 30 分钟 sustained；2 小时作为目标验收。
- 最终系统能力必须按 05K 完成 resident service smoke/required；未完成时只能写 `post_detector_chain_pass`、`single_shot_model_smoke` 或 `interface_smoke`。
- 最终项目完成还必须按 05L 完成独立代码库验收；若仍直接耦合项目三/四脚本，只能写 `artifact_replay_pass` 或 `legacy_adapter_smoke`，不能写完整在线系统完成。
- `failure_and_fallback.md` 明确每类失败的回退行为。
- 至少 3 个真实系统整合问题或风险项进入 `troubleshooting.md`；如果未触发真实失败，也要记录已检查风险。

## 风险与降级方案

| 风险 | 降级方案 | 必须保留的证据 |
|---|---|---|
| 项目四准入未完成 | 对应模型设为 `blocked`，用 stub 联调接口 | 缺失报告、阻塞原因、后续补测项 |
| VLM 太慢 | 只处理高置信度事件、只传 ROI、降低分辨率、异步调用 | 延迟、内存、超时率、队列影响 |
| 视频理解未准入或太慢 | 禁用视频模型；使用检测/抽帧/ROI 摘要，或另开专项复测 | 片段路径、fallback 状态、summary 来源 |
| LLM 超时 | 规则模板告警、缩短 prompt、降低 max token | 超时日志、fallback JSON |
| JSON 不合格 | schema 修复器或模板回退 | 原始输出、修复后输出、冲突记录 |
| 8GB 内存不足 | 禁用 VLM/视频、降低上下文、关闭并发 | 内存、swap、温度、恢复结果 |
| 检测被阻塞 | 队列隔离、丢弃低优先事件、限频 LLM/VLM | 队列长度、drop count、检测 FPS |
| 摄像头断流 | 重连、切换固定视频、进入 degraded 状态 | 断流时间、恢复时间、丢帧数 |

## 2026-07-13 工程增量

这一轮不再新增新的目标板或新的模型路线，而是围绕现有 Project5 本地常驻服务做两件事：

1. **RK3588 优化运行卫生**
   - `run_rk3588_p7_resident_service_smoke.sh`
   - `run_rk3588_p8_resident_service_required.sh`
   - `run_rk3588_p9_resident_service_target.sh`

   上述三个 wrapper 默认 `FRAME_CACHE_CAPACITY` 已由 `4096` 收紧到 `512`，并且 `CLEAN_FRAME_CACHE_ON_EXIT=1` 时会在 `EXIT` 路径统一删除 `*_frame_cache/`。
   这次优化针对的是“内部 ring buffer 留存太多 JPEG”问题，不改变最终 alarm JSON 的事实字段，也不降低 resident text/VLM 的功能边界。

2. **Jetson 收口真实阻塞点**
   - `run_alarm_service.py` 与 `detector_service.py` 新增 detector 冷启动重试：
     - `--detector-start-retries`
     - `--detector-restart-delay-sec`
   - `run_alarm_service.py` 与 `vlm_worker.py` 新增 resident VLM 请求级重试：
     - `--vlm-request-retries`
   - `run_jetson_p6_resident_vlm_smoke.sh` 默认改为：
     - `VLM_TIMEOUT_MS=180000`
     - `VLM_IMAGE_MIN_TOKENS=768`
     - `VLM_IMAGE_MAX_TOKENS=768`
     - `VLM_REQUEST_RETRIES=1`
   - `run_jetson_p7_resident_service_smoke.sh` / `run_jetson_p8_resident_service_required.sh` 默认继续保持 CPU-first，并进一步把 VLM 预算收紧到更适合告警摘要的水平。

### 当前结论

| 板卡 | 当前主线状态 | 下一步 |
|---|---|---|
| RK3588 8GB | 单板 resident detector + resident text/VLM + P7/P8/P9 已具备证据，当前进入“减产物、保稳定”的优化阶段 | 用新参数复跑，确认 `frame_cache_cleanup=done` 且长稳不退化 |
| Jetson 8GB | resident detector 已通过，resident text 已通过；resident VLM 与单板并发仍未收口 | 先跑 P6 resident VLM v4，再跑 P7 concurrency v4 |
