# failure_and_fallback

当前状态：`jetson_required30min_fallback_policy_verified_rk3588_resident_detector_smoke_verified_rkllm_text_astra_camera_and_real_vlm_mt384_verified`。

本报告记录项目五系统整合中的失败、降级和恢复策略。项目四已经暴露的模型准入限制必须直接进入项目五 fallback 策略，不能在项目五报告中重新写成可用能力。

## 降级策略总表

| 问题 | 触发条件 | 降级动作 | 输出状态 | 证据 |
|---|---|---|---|---|
| Jetson 视频理解不准入 | SmolVLM2 多帧视频为 `D_not_used` | 不调用视频模型；用检测/抽帧/ROI 摘要生成 `video_summary` | `disabled_by_project4_decision` | project4 decision + `video_understanding_benchmark.md` |
| Jetson VLM 延迟过高 | Qwen3-VL project4 p95 约 `33.11s` 或项目五 timeout | 跳过 VLM，保留检测事实和文本解释 | `vlm_timeout` / `skip_vlm` | project4 Qwen3-VL benchmark; required30min route stub verified |
| Jetson LLM 延迟不可接受 | Qwen3 text 超过 `10000 ms` 或队列堆积 | 模板告警 JSON；降低 LLM 频率 | `llm_timeout_template` | project4 Qwen3 benchmark; required30min Qwen3 rows=10 bad=0 |
| RK3588 视频理解不准入 | SmolVLM2 视频路线不进入项目五主线 | 不调用视频模型；用检测/抽帧/ROI 摘要生成 `video_summary` | `disabled_by_project4_decision` | project4 decision + `video_understanding_benchmark.md` |
| RK3588 VLM 延迟过高 | Qwen3-VL project4 p95 约 `57.2s` 或项目五 timeout | 跳过 VLM，保留检测事实和文本解释 | `vlm_timeout` / `skip_vlm` | project4 Qwen3-VL RKNN/RKLLM benchmark; Project5 required/Astra camera use route stub |
| 真实 VLM 图片资产缺失 | event package 只有 `roi_boxes`，`keyframe_path`/`roi_paths` 为空或路径不存在 | 不执行真实 VLM；先用 `SAVE_OUTPUT_VIDEO=1` 重跑 Project3 并抽帧/裁 ROI | `blocked_no_image_asset` / `fixed_by_asset_extraction` | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` 已验证 3 event assets + 5 ROI images |
| VLM 输出截断 | 多目标事件 prompt 较长且 `--max-tokens=128` | 已提高到 `--max-tokens=384` 并复跑；后续正式引用 mt384 raw | `fixed_by_max_tokens_384` | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1_vlm_outputs_mt384.jsonl` rows=3, bad=0 |
| RK3588 LLM 延迟不可接受 | Qwen3 RKLLM p95 约 `26.63s` 或队列堆积 | 模板告警 JSON；降低 LLM 频率 | `llm_timeout_template` | project4 Qwen3 RKLLM benchmark; project5 RKLLM text smoke rows=3 bad=0 |
| RK3588 RKLLM 输出污染 | RKLLM runtime banner 混入 stdout/stderr | 清洗 runtime 日志后再写入 `llm_explanation`；残留污染则不判 pass | `fixed_by_rkllm_output_cleanup` | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` |
| JSON 不合格 | alarm JSON schema fail | 保留原始输出，schema repair 或模板重建 | `json_repaired` | alarm schema + project5 alarm raw pending |
| 检测队列堆积 | queue_depth 超阈值或 drop_count 上升 | 丢弃低优先事件，暂停 VLM，限制 LLM | `queue_degraded` | time-window raw pending |
| 摄像头/视频断流 | 输入无帧或读取错误 | 重连或切换固定视频，进入 degraded | `source_degraded` | failure injection pending |
| 内存/swap 过高 | swap 或 memory 超阈值 | 禁用 VLM/视频，降低上下文和输出 token | `resource_degraded` | monitor log pending |
| 温控/功耗异常 | 温度升高或功耗模式不明 | 限频低频模型，保留检测主线 | `thermal_degraded` | monitor log pending |

## Jetson 已知准入风险

| issue_id | date | board | source | module | symptom | fallback | project5 impact | status |
|---|---|---|---|---|---|---|---|---|
| P05-JETSON-VIDEO-DISABLED-001 | 2026-07-04 | Jetson 8GB | project4 decision | video | SmolVLM2 多帧视频不准入 | 禁用视频模型；检测/抽帧摘要替代 | `video_summary` 不能写成模型视频理解 | `policy_frozen` |
| P05-JETSON-VLM-LATENCY-001 | 2026-07-04 | Jetson 8GB | project4 Qwen3-VL formal v2 | vlm | ROI/image VLM p95 约 `33.11s` | 仅低频异步；超时跳过 | 不能逐帧或同步阻塞检测 | `policy_frozen` |
| P05-JETSON-LLM-LOWFREQ-001 | 2026-07-04 | Jetson 8GB | project4 Qwen3 text formal | llm | 文本 p95 约 `6.37s` | 事件触发异步；超时模板 | 不能写成强实时文本解释 | `policy_frozen` |
| P05-JETSON-CONCURRENCY-PENDING-001 | 2026-07-04 | Jetson 8GB | project5 gap | system | 项目四未验证检测+LLM/VLM 并发 | 已完成 Jetson 30min 后处理链路；完整常驻并发服务仍不声明 | Jetson required30min pass_with_caveat；RK3588 仍待执行 | `jetson_required30min_pass_with_caveat` |
| P05-JETSON-LLAMA-CAPTURE-001 | 2026-07-07 | Jetson 8GB | project5 text smoke | llm | llama.cpp 交互 TTY 有输出但 Python stdout/stderr 未捕获，旧 raw 可能为空或误收 `--no-conversation` 错误 | 使用 util-linux `script` 会话捕获；解析 `[End thinking]` 后最终四行 | 真实 Qwen3 文本 smoke 已恢复，仍需覆盖旧失败 raw | `fixed_by_script_capture` |
| P05-JETSON-REQUIRED30MIN-PASS-001 | 2026-07-08 | Jetson 8GB | project5 required30min | system | 30 分钟 required run 已完成，VLM 为 route stub，video disabled，power_w unavailable | 保留检测事实和 Qwen3 文本解释；VLM/video 按策略降级 | Jetson 项目五 required30min 判定通过，但不声明真实 VLM 项目五性能和完整并发服务 | `pass_with_caveats` |
| P05-RK3588-VIDEO-DISABLED-001 | 2026-07-04 | RK3588 8GB | project4 decision | video | SmolVLM2 视频主线不准入 | 禁用视频模型；检测/抽帧摘要替代 | `video_summary` 不能写成模型视频理解 | `policy_frozen` |
| P05-RK3588-VLM-LATENCY-001 | 2026-07-04 | RK3588 8GB | project4 Qwen3-VL formal v2 | vlm | ROI/image VLM p95 约 `57.2s` | 仅低频异步；超时跳过 | 不能逐帧或同步阻塞检测 | `policy_frozen` |
| P05-RK3588-LLM-LOWFREQ-001 | 2026-07-04 | RK3588 8GB | project4 Qwen3 RKLLM formal | llm | 文本 p95 约 `26.63s` | 事件触发异步；超时模板 | 不能写成强实时文本解释 | `policy_frozen` |
| P05-RK3588-CONCURRENCY-PENDING-001 | 2026-07-04 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | system | 项目四未验证检测+LLM/VLM 并发 | 已完成 30min detector/event/template/VLM stub/Alarm JSON/per-event/stability schema，并补齐 resident detector smoke；必须继续跑真实 resident/warm RKLLM/RKNN-VLM | 当前不能声明真实模型系统验收通过 | `resident_detector_smoke_pass_concurrent_models_pending` |
| P05-RK3588-RESIDENT-DETECTOR-PARTIAL-JSON-001 | 2026-07-10 | RK3588 8GB | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v1` | service/detector tail | resident service 在线 tail 在 detector 追加 JSONL 时提前解析了未换行半行，报 `invalid JSON: Unterminated string` | 在 `detector_service.py` 增加 partial-line guard；仅当行已完整或 detector 已退出时才解析 | v2 复跑 600.885s pass；四类 schema 全部 pass | `fixed_by_tail_partial_line_guard` |
| P05-RK3588-PROJECT3-SCHEMA-PLAYLIST-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_smoke_v1_project3_detector` | schema | 板端 schema allowed set 缺少 `video_playlist` | 更新 `benchmark/schemas/video_pipeline_raw_schema.yaml` 后只重跑 schema check | detector raw 无需重跑；schema check pass | `fixed_by_schema_allowed_set_update` |
| P05-RK3588-ALARM-SCHEMA-PATH-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_smoke_v1` | schema | 临时命令引用不存在的 `benchmark/schemas/alarm_output_schema.json` | 使用 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json` 复验 | Alarm JSON rows=75，schema pass | `fixed_by_correct_schema_path` |
| P05-RK3588-RKLLM-OUTPUT-CLEANUP-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | llm | runtime banner 混入 `llm_explanation` | Project5 RKLLM 适配器清洗 runtime 日志；污染残留不判 pass | 复跑 rows=3 bad=0 contaminated=0 | `fixed_by_rkllm_output_cleanup` |
| P05-RK3588-ASTRA-CAMERA-SMOKE-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | camera/system | Astra S camera source 触发 2 条人员候选事件 | 保留真实 RKLLM 文本解释；VLM route stub；video disabled | event/alarm/per-event schema pass，LLM rows=2 bad=0 contaminated=0 | `camera_alarm_chain_smoke_pass_with_vlm_stub` |
| P05-REAL-VLM-ASSET-PENDING-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` | vlm/assets | 旧 event package 只有 bbox/roi_boxes，没有真实 `keyframe_path`/`roi_paths` 图片；mt128 曾截断多目标输出 | 已用 `SAVE_OUTPUT_VIDEO=1` 生成 Project3 output video，再抽帧裁 ROI，并以 mt384 复跑真实 VLM | event-assets rows=3 schema pass; ROI images=5; real VLM mt384 rows=3 pass, bad=0 | `fixed_by_asset_extraction_and_mt384_quality_regression` |

| P05-RK3588-VIDEO-DISABLED-001 | video_vlm 按项目四结论禁用 | `20260708_rk3588_8gb_alarm_system_smoke_v1` | interface pass | Alarm JSON rows=75 schema pass; fallback_count=75 reflects VLM/video boundary, not system error |
| P05-RK3588-VIDEO-DISABLED-001 | video_vlm 按项目四结论禁用 | `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | required interface pass | Alarm JSON rows=200 schema pass; fallback_count=200 reflects VLM/video boundary, not system error |

## 失败记录

| issue_id | date | board | run_id | module | symptom | fallback | recovery | status |
|---|---|---|---|---|---|---|---|---|
| P05-JETSON-REQUIRED30MIN-PASS-001 | 2026-07-08 | Jetson 8GB | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | detector/event/llm/vlm/json/stability | 无阻断失败；VLM route stub、video disabled、power_w unavailable | 按策略保留检测事实和 Qwen3 文本解释，VLM/video 降级 | event/alarm/per-event/stability schema 全部 pass | `pass_with_caveats` |
| P05-RK3588-RESIDENT-DETECTOR-PARTIAL-JSON-001 | 2026-07-10 | RK3588 8GB | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v1` | service/detector tail | service 在线读取 `resident_detector.jsonl` 时命中未完成 JSON 行，1 秒内退出 | 当前事件窗口直接失败，不允许复用旧 raw 继续判定 | `p05_tail_guard_v2` 修复后以 `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` 复跑通过 | `fixed_and_regressed_pass` |

## 回归检查

| issue_id | fix | regression run | result | evidence |
|---|---|---|---|---|
| P05-JETSON-VIDEO-DISABLED-001 | alarm JSON 写 `fallback_status.video=disabled_by_project4_decision` | `20260704_jetson_8gb_alarm_system_smoke_v1` | interface pass | alarm JSON schema pass rows=542; per-event raw schema pass rows=542 |
| P05-JETSON-VLM-LATENCY-001 | VLM 低频异步 + timeout | `20260704_jetson_8gb_alarm_system_smoke_v1` | interface only | VLM stub output rows=20; no model execution |
| P05-JETSON-LLM-LOWFREQ-001 | LLM 低频异步 + template fallback | `20260704_jetson_8gb_alarm_system_smoke_v1` | interface only | LLM template output rows=542; no model execution |
| P05-JETSON-VIDEO-DISABLED-001 | alarm JSON 写 `fallback_status.video=disabled_by_project4_decision` | `20260704_jetson_8gb_alarm_system_local_dryrun` | interface pass | alarm JSON schema pass; per-event raw schema pass |
| P05-JETSON-VLM-LATENCY-001 | VLM 低频异步 + timeout | `20260704_jetson_8gb_alarm_system_local_dryrun` | interface only | VLM stub output rows=5; no model execution |
| P05-JETSON-LLM-LOWFREQ-001 | LLM 低频异步 + template fallback | `20260704_jetson_8gb_alarm_system_local_dryrun` | interface only | LLM template output rows=5; no model execution |
| P05-JETSON-LLAMA-CAPTURE-001 | `run_llm_explain.py` 增加 `--capture-mode script` 和 `--session-log-dir` | `20260705_jetson_8gb_alarm_system_text_smoke_v1` | pass | Qwen3 text rows=10; bad rows=0; first capture mode=`script`; first raw present=True |
| P05-JETSON-LLM-LOWFREQ-001 | 真实 Qwen3 文本解释低频 smoke | `20260705_jetson_8gb_alarm_system_text_smoke_v1` | text smoke pass | LLM rows=10; no fallback in checked rows; thinking output preserved in raw and final four-line explanation extracted |
| P05-JETSON-VIDEO-DISABLED-001 | video_vlm 按项目四结论禁用 | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | pass | Alarm JSON rows=397 schema pass; fallback_count=397 reflects VLM/video boundary, not system error |
| P05-JETSON-VLM-LATENCY-001 | VLM 保持低频 route stub，不阻塞检测主线 | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | pass_with_stub | VLM rows=3 route stub; Project3 detector FPS `30.0722`; drop_count=0 |
| P05-JETSON-LLM-LOWFREQ-001 | 真实 Qwen3 文本低频解释，util-linux `script` 捕获 | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | pass | LLM rows=10; bad rows=0; first capture mode=`script`; Alarm JSON rows=397 schema pass |
| P05-JETSON-CONCURRENCY-PENDING-001 | 30 分钟 required 后处理链路验证 | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | pass_with_caveat | detector 54130 frames pass; event/alarm/per-event/stability schema pass; not a fully concurrent resident service claim |
| P05-RK3588-LLM-LOWFREQ-001 | 真实 RKLLM 文本低频解释接入 Project5 适配器 | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | pass | LLM rows=3; bad rows=0; first total `14804.1 ms`; first decode `13.3427 tok/s`; Alarm JSON rows=200 schema pass |
| P05-RK3588-RKLLM-OUTPUT-CLEANUP-001 | 清洗 RKLLM runtime banner 后再写入 `llm_explanation` | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | pass | contaminated rows=0; event package/alarm JSON/per-event raw schema pass |
| P05-RK3588-VIDEO-DISABLED-001 | Astra S camera run 继续记录 video disabled / VLM stub 降级边界 | `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | pass_with_stub | events=2; real RKLLM rows=2; VLM route stub rows=2; Alarm JSON rows=2 schema pass |
| P05-RK3588-RESIDENT-DETECTOR-PARTIAL-JSON-001 | `detector_service.py` 增加 partial-line guard，仅在换行完成后解析在线 JSONL | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` | pass | resident detector raw rows=18048; window_sec=600.885; events=75; alarms=75; drop_count=0; four schema checks pass |
