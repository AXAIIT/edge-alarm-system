# board_matrix

当前状态：`dual_board_target_pass_publishable_text_guard_pass`。

本报告记录项目五模型组合和准入边界。项目四 selected run 可以作为模型准入输入，但不能替代项目五端到端系统 run。截止 `2026-07-18`，RK3588 已完成单板 `P7/P8/P9`，Jetson 已完成 resident detector smoke、resident text/VLM standalone smoke，以及 accepted Route B postrun 的单板 `P7/P8/P9`；双板 `required` 已由 `20260716_p05_dual_board_required_v1` 补齐，双板 `target` 已由 `20260717_p05_dual_board_target_v1` 补齐。该 target run 两板启动相差 `22.5s`、有效重叠 `7194.72s`，超过 `6900s` 门槛，组级状态为 `dual_board_target_ready`。`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` 已补齐 Jetson resident text 的事实约束回放；主线不再存在未关闭验收项。

2026-07-14 更新：Jetson 当前推荐收口顺序已经改成两条分层路线，而不是默认继续追三常驻同窗。先做 `detector resident + VLM resident + text template`，再做 `detector resident + text resident` 实时链路，最后把 VLM 退到异步 enrichment。原因是 Jetson 当前剩余阻塞点已经收口到 multimodal request path，继续无差别复跑旧 P7/P8 的信息增益太低。
同日最新板端结果已把这一路线再收紧一层：Route A `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` 虽然达成 `window_requirement_met=true`、`event_count=136`、`alarm_count=136`、`drop_count=0`，但两次真实图片请求仍全部 timeout；Route B realtime `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` 则已跑通 `detector + resident text + VLM stub`，`window_sec=612.872`、`detection_fps=29.448237`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`，说明 Jetson 实时主链路已经可以收口到 `detector + resident text`。但该 run 的第 2 条真实文本解释把 `vehicle_presence/car` 错写成“未佩戴安全帽”，因此它当前只能声明 runtime pass，不能直接声明语义质量 pass。Route B async enrichment `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 又证明：即使把 resident text 从链路里完全拆掉，`events_input + resident VLM` 的真实图片请求仍然两次 timeout。也就是说，Jetson 当前还剩两个独立问题：resident VLM request path 未通过，以及 resident text 在收紧 token/prompt 后已经出现事实漂移。

## 项目四准入输入

| 输入报告 | 状态 | 说明 |
|---|---|---|
| `projects/04_llm_vlm_independent/reports/llm_vlm_model_matrix.md` | `available` | 三板模型可行性矩阵，含 selected run、raw/log/monitor；项目五主线只保留 Jetson/RK3588 |
| `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` | `available` | 项目五准入等级和降级策略 |
| `projects/04_llm_vlm_independent/reports/troubleshooting.md` | `available` | 模型失败、OOM、fallback 和 blocked 路线 |

## 双板模型组合

| board | detector | detector backend | text LLM | image VLM | video model | 项目四等级 | 项目五系统状态 | 证据 |
|---|---|---|---|---|---|---|---|---|
| Jetson 8GB | YOLO11n INT8 | TensorRT | Qwen3-1.7B GGUF Q4_K_M | Qwen3-VL-2B-Instruct Q4_K_M GGUF + mmproj F16 | SmolVLM2 多帧视频禁用；以检测/抽帧摘要替代 | text=`B_low_frequency`; image=`B_low_frequency`; video=`D_not_used` | `resident_service_target_pass_route_b_postrun_publishable_text_guard_pass`; 已完成 Project5 本地 resident detector 10 分钟 smoke、Jetson resident text/VLM standalone smoke；`20260717_jetson_8gb_alarm_service_route_b_target_v3` 完成 accepted Route B postrun 单板 target，async VLM 严格 `2/2 pass`；`20260717_p05_dual_board_target_v1_jetson` 作为双板 target 槽位完成 `7217.22s`、`30.000887 FPS`、`drop=0`。`20260718...text_fact_guard_smoke_v3` 用同一 text server 一次加载完成三次 no-think 请求，所有冲突原文均保留审计并以 detector-fact 模板安全发布。 | `projects/05_alarm_system/configs/models/jetson_model_combo.yaml`; `20260717_jetson_8gb_alarm_service_route_b_target_v3`; `20260717_p05_dual_board_target_v1_jetson`; `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3`; project4 decision |
| RK3588 8GB | YOLO11n | RKNN | Qwen3-1.7B RKLLM W8A8 | Qwen3-VL RKNN vision + RKLLM decoder W8A8 | SmolVLM2 视频禁用；以检测/抽帧摘要替代 | text=`B_low_frequency`; image=`B_low_frequency`; video=`D_not_used` | `resident_service_target_pass_with_resident_text_vlm_workers`; Project5 local resident detector、resident text worker、resident VLM worker 均已有板端证据，Astra S camera alarm-chain 和 frame-cache asset smoke 已过，真实 VLM ROI smoke rows=3 pass，并已完成单板 10 分钟同窗并发 smoke、30 分钟 required、2 小时 target，且在 `20260717_p05_dual_board_target_v1_rk3588` 作为双板 target 槽位完成 `7203.72s`、`30.042395 FPS`、LLM/VLM 各 `2` 次、`drop=0`。 | `projects/05_alarm_system/configs/models/rk3588_model_combo.yaml`; `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2`; `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1`; `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1`; `20260711_rk3588_8gb_alarm_service_camera_frame_cache_smoke_v1`; `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3`; `20260713_rk3588_8gb_alarm_service_resident_required_v2`; `20260713_rk3588_8gb_alarm_service_resident_target_v2`; `20260717_p05_dual_board_target_v1_rk3588`; project4 decision |

RDK X5 8GB 因项目四失败结论从项目五主线删除，不进入后续系统 benchmark、稳定性和 selected run。

## Jetson Selected Combo

| role | selected item | selected run / baseline | inherited metric | project5 use |
|---|---|---|---|---|
| detector | YOLO11n TensorRT INT8 PTQ | `20260617_jetson_8gb_yolo11n_tensorrt_int8_runtime600_playlist20_noout` | 约 `30.0872 FPS`; p95 `49.1965 ms`; p99 `52.2379 ms` | 高频检测主线，LLM/VLM 不能阻塞 |
| detector stability | YOLO11n TensorRT INT8 PTQ | `20260617_jetson_8gb_yolo11n_tensorrt_stability_acceptance_playlist80_noout` | `7196s`; `30.0573 FPS`; p95 `52.0953 ms`; drop rate `0.00051` | 继承为检测稳定性基线 |
| text LLM | Qwen3-1.7B GGUF Q4_K_M | `20260626_jetson_8gb_qwen3_1_7b_q4_k_m_gguf_llamacpp_cuda_text_ctx512_formal_v1` | p95 `6370.1 ms`; decode `29.345 tok/s`; memory peak `2146 MB`; swap `218 MB` | `B_low_frequency`; 事件触发异步文本解释 |
| image VLM | Qwen3-VL-2B-Instruct Q4_K_M + mmproj F16 | `20260628_jetson_8gb_qwen3_vl_2b_q4_k_m_gguf_llamacpp_cuda_image_multi_input_formal_v2_mmproj_offload` | p50 `24120.0 ms`; p95 `33107.15 ms`; memory peak `3777 MB`; swap `214 MB` | `B_low_frequency`; ROI/关键帧低频异步，不逐帧 |
| video understanding | SmolVLM2-500M-Video-Instruct | `none_for_multiframe_video` | 多帧任务失败，context/media slot 不足 | `D_not_used`; `fallback_status.video=disabled_by_project4_decision` |

## RK3588 Selected Combo

| role | selected item | selected run / baseline | inherited metric | project5 use |
|---|---|---|---|---|
| detector | YOLO11n RKNN INT8 | 项目三 RK3588 selected detector run | 项目三 runtime/stability 报告为准 | 高频检测主线，LLM/VLM 不能阻塞 |
| text LLM | Qwen3-1.7B RKLLM W8A8 | `20260701_rk3588_8gb_qwen3_1_7b_rkllm_text_ctx2048_formal_v2 + quality_v1 + quality_v2`; Project5 `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1`; Project5 camera `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1`; Project5 resident text `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1` | project4 p50 约 `15168.15 ms`; p95 `26628.865 ms`; decode `12.712 tok/s`; Project5 required-event smoke first checked row `14804.1 ms` / `13.3427 tok/s`; resident text worker first row `11622.3 ms` / `12.7379 tok/s`，同一 `resident_server_pid`、`model_load_count=1`; Astra camera first checked row `13645.6 ms` / `12.2845 tok/s`; bad=0 | `B_low_frequency`; 事件触发异步文本解释，single-shot 与 resident-text worker smoke 均已具备 |
| image VLM | Qwen3-VL-2B-Instruct RKNN vision 384 + RKLLM decoder W8A8 | `20260703_rk3588_8gb_qwen3_vl_2b_rknn_rkllm_image_cn_formal_v2_max512`; Project5 `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` | project4 p50 `21391.0 ms`, p95 `57199.9 ms`; Project5 mt384 ROI smoke total `20172/28550/17747 ms`, decode `9.9667/8.6903/9.1223 tok/s`, rows=3 pass；历史 128-token 截断已修复 | `B_low_frequency`; ROI/关键帧低频异步，不逐帧；当前是 once 调用，不是 resident VLM |
| video understanding | SmolVLM2-500M-Video-Instruct | `none_for_project5_video` | 项目四只保留诊断/失败证据；视频主线不准入 | `D_not_used`; `fallback_status.video=disabled_by_project4_decision` |

## 接入规则

| 等级 | 项目五使用方式 |
|---|---|
| `A_mainline` | 可进入默认链路，但仍需系统并行复测 |
| `B_low_frequency` | 只允许事件触发、异步、排队或人工触发 |
| `C_offline` | 只做离线分析、报告展示或诊断 |
| `D_not_used` | 不接入项目五能力链路 |
| `not_executed` / `not_decided` / 空白 | 项目五标记 `blocked` 或 `pipeline_pending` |

## Jetson 复测项

| item | reason | required project5 evidence | status |
|---|---|---|---|
| Detector + LLM 并行资源冲突 | 项目四只测单模型，项目三只测检测 | per-event raw、monitor log、检测 FPS delta、queue_depth/drop_count | `pass_with_caveat`; detector 30min pass + Project5 后处理链路 pass，不声明完整常驻并发服务 |
| 真实 ROI 输入链路 | Qwen3-VL formal v2 使用固定图片/ROI，不是项目五事件 ROI | event package、ROI crop latency、VLM raw、manual quality | `route_stub_only`; 本轮不声明真实 Project5 VLM 性能 |
| 结构化告警 JSON | 项目四不生成项目五 alarm JSON | alarm JSON schema pass、fact conflict check、json_repair_count | `pass_schema`; rows=397 |
| 30 分钟项目五稳定性 | 项目三稳定性只覆盖检测链路 | time-window raw、monitor、fallback/error/restart count | `pass`; window_sec=3223.0, events=397, alarms=397, errors=0 |
| 视频理解降级路径 | SmolVLM2 D_not_used | `video_summary` 替代策略和 fallback 状态 | `pass_policy`; video disabled by project4 decision |

## RK3588 待复测项

| item | reason | required project5 evidence | status |
|---|---|---|---|
| Detector + LLM/VLM 并行资源冲突 | 项目四只测单模型或模型组合，项目三只测检测 | per-event raw、monitor log、检测 FPS delta、queue_depth/drop_count | `resident_service_smoke_pass_with_resident_text_vlm_workers_not_required`; `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` 已证明 resident detector 与 resident text/VLM 可在同一 603.714s 窗口共存，`detection_fps=29.89495`、`event_queue_depth=19`、`drop_count=0`；随后 `20260713_rk3588_8gb_alarm_service_resident_required_v2` 与 `20260713_rk3588_8gb_alarm_service_resident_target_v2` 已把这条链路扩展到 30 分钟 required 和 2 小时单板 target |
| RK3588 Qwen3-VL 低频 ROI 链路 | 项目四 image/ROI p95 约 `57.2s`，只能低频 | event package、ROI crop latency、VLM raw、timeout/fallback | `real_vlm_runtime_smoke_pass_mt384_quality_pass_single_shot`; `events_with_assets` rows=3，ROI images=5，VLM mt384 rows=3 pass；不是 resident VLM |
| 结构化告警 JSON | 项目四不生成项目五 alarm JSON | alarm JSON schema pass、fact conflict check、json_repair_count | `pass_required_interface_and_rkllm_text_smoke_and_camera_chain`; required Alarm JSON rows=200 schema pass；RKLLM text smoke Alarm JSON rows=200 schema pass；Astra camera Alarm JSON rows=2 schema pass |
| 30 分钟项目五稳定性 | 项目三稳定性只覆盖检测链路 | time-window raw、monitor、fallback/error/restart count | `resident_service_required_pass_with_resident_text_vlm_workers`; resident detector smoke window_sec=600.885、P7 smoke window_sec=603.714、P8 required window_sec=1803.685、`llm_call_count=2`、`vlm_call_count=2`、`drop_count=0`；真实 RKLLM/VLM 30 分钟并发稳定性已由 `20260713_rk3588_8gb_alarm_service_resident_required_v2` 补齐 |
| 2 小时 resident service target | 已完成双板 2 小时 target 有效重叠 | `resident_service_target` wrapper/direct run、7200s time-window raw、monitor、restart/recovery 记录 | `20260717_p05_dual_board_target_v1`：Jetson `7217.22s`、`30.000887 FPS`、`1550 alarms`、`drop_count=0`；RK3588 `7203.72s`、`30.042395 FPS`、`765 alarms`、LLM/VLM 各 `2` 次、`drop_count=0`；启动差 `22.5s`、有效重叠 `7194.72s`、`aggregate_status=dual_board_target_ready` |
| 视频理解降级路径 | SmolVLM2 不进入项目五视频主线 | `video_summary` 替代策略和 fallback 状态 | `policy_pass`; video disabled by project4 decision，Alarm JSON fallback 字段待验证 |
## 2026-07-13 Delta

### Jetson

- 不再把 Jetson resident VLM 写成“只有代码、没有板端结果”。
- 当前最新板端状态应拆成三条：
  1. `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4`：standalone resident VLM 已通过，`vlm_bad_rows=0`；
  2. `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v3`：历史失败证据，detector 在首个 JSONL 之前即出现 TensorRT/CUDA 初始化失败；
  3. `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8`：有效 10 分钟时间窗已达成，但真实 resident VLM request 仍分别出现 `RemoteDisconnected` 和 `timeout`。

### RK3588

- 单板 `resident_service_smoke`、`resident_service_required`、`resident_service_target` 已具备有效证据。
- 当前工程优化重点已经从“证明可运行”转为“减少 frame-cache JPEG 留存、保证失败时自动清理”。
