# troubleshooting

当前状态：`dual_board_target_pass_publishable_text_guard_pass`。

本文件记录项目五问题库。当前已先把项目四对 Jetson 项目五有直接影响的真实限制转成项目五风险项；项目五 selected run 执行后，所有失败、超时、OOM、JSON 不合格和队列问题必须继续追加。

## 问题索引

| issue_id | date | board | run_id | module | severity | status | summary |
|---|---|---|---|---|---|---|---|
| P05-JETSON-VIDEO-DISABLED-001 | 2026-07-04 | Jetson 8GB | none_for_project5_yet | video | P1 | `policy_frozen` | SmolVLM2 多帧视频在项目四为 `D_not_used`，项目五不得接入视频理解模型 |
| P05-JETSON-VLM-LATENCY-001 | 2026-07-04 | Jetson 8GB | project4 selected run | vlm | P2 | `policy_frozen` | Qwen3-VL p95 约 `33.11s`，只能低频异步 ROI/关键帧调用 |
| P05-JETSON-LLM-LOWFREQ-001 | 2026-07-04 | Jetson 8GB | project4 selected run | llm | P2 | `policy_frozen` | Qwen3-1.7B 文本 p95 约 `6.37s`，不能写成强实时文本解释 |
| P05-JETSON-CONCURRENCY-PENDING-001 | 2026-07-04 | Jetson 8GB | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | system | P1 | `jetson_required30min_pass_with_caveat` | Jetson 已完成 30min 后处理链路验证；完整并发常驻服务仍不声明，RK3588 仍需实测 |
| P05-JETSON-SMOKE-STUB-001 | 2026-07-04 | Jetson 8GB | `20260704_jetson_8gb_alarm_system_smoke_v1` | system | P2 | `open_pending_real_model_run` | 结构化链路 smoke 已通过 542 行 schema，但 LLM 为 template、VLM 为 stub、无 monitor/ROI/clip |
| P05-JETSON-TASK-DOMAIN-SCHEMA-001 | 2026-07-04 | Jetson 8GB | `20260704_jetson_8gb_alarm_system_v3_task_domain_local_check` | schema | P2 | `contract_updated` | 新增 `alarm_domain` 后，v3 本地检查已通过 event package、alarm JSON、per-event raw 三类 schema |
| P05-JETSON-LLAMA-CAPTURE-001 | 2026-07-07 | Jetson 8GB | `20260705_jetson_8gb_alarm_system_text_smoke_v1` | llm | P1 | `fixed_by_script_capture` | llama.cpp 真实输出写入交互 TTY，旧 stdout/stderr 捕获链路无法稳定写入 JSON；已改为 util-linux `script` 会话捕获 |
| P05-JETSON-TEXT-SMOKE-001 | 2026-07-07 | Jetson 8GB | `20260705_jetson_8gb_alarm_system_text_smoke_v1` | system | P2 | `not_verified_text_model_smoke` | 真实 Qwen3 文本解释 10 条 smoke 通过，Alarm JSON/per-event raw 136 行 schema pass；VLM 仍为 stub，无 monitor/稳定性 |
| P05-JETSON-PROJECT3-RAW-PATH-001 | 2026-07-07 | Jetson 8GB | `20260707_jetson_8gb_alarm_system_stability_smoke_v1` | input | P2 | `fixed_by_explicit_raw_selection` | stability smoke 最初假设存在 `20260705..._detector.jsonl`，实际 Jetson 只有 `20260704..._detector.jsonl`；流程已改为先 `find` 再设置 `PROJECT3_RAW` |
| P05-JETSON-STABILITY-SMOKE-001 | 2026-07-07 | Jetson 8GB | `20260707_jetson_8gb_alarm_system_stability_smoke_v1` | stability | P2 | `not_verified_raw_replay_stability_smoke` | raw replay stability smoke 采集 553 行 tegrastats，四类 schema pass；仍非实时服务 10 分钟和非 30 分钟 required |
| P05-JETSON-REALTIME10MIN-MONITOR-001 | 2026-07-08 | Jetson 8GB | `20260707_jetson_8gb_alarm_system_realtime10min_v1` | stability | P2 | `accepted_with_caveat` | Project3 detector 10min pass，Project5 链路到 Alarm JSON 完成；E2E monitor 窗口 51112s 过长，用户裁定本轮通过但需保留 caveat |
| P05-JETSON-REQUIRED30MIN-PASS-001 | 2026-07-08 | Jetson 8GB | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | stability | P1 | `pass_with_caveats` | Project3 detector 30min pass，Project5 event/alarm/per-event/stability schema 全部 pass；VLM 为 route stub，video disabled，power_w unavailable |
| P05-JETSON-RESIDENT-VLM-CUDA-OOM-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v2` | llama.cpp / vlm | P1 | `startup_oom_reproduced_request_timeout_after_reboot` | Jetson resident text 已启动成功；首次并发 run 的 resident VLM 在启动阶段对 CUDA0 申请 450.60 MiB buffer 失败；重启后 standalone P6-VLM 已能启动，但首个图片请求仍超时 |
| P05-JETSON-RESIDENT-VLM-REQUEST-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v3`; `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8`; `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1`; `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` | llama.cpp / vlm request | P1 | `standalone_pass_but_route_a_and_async_request_failures_reproduced` | Jetson standalone resident VLM 已在 `v4` 通过；但 `v8` 并发窗口、`20260714` Route A 以及 `20260714` async enrichment 中，真实图片请求都仍失败，说明问题已收口到 multimodal request path 本身 |
| P05-JETSON-RESIDENT-TEXT-FACT-DRIFT-001 | 2026-07-14 | Jetson 8GB | `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1`; local `test_fact_guard.py` | llama.cpp / text quality | P1 | `guard_implemented_board_replay_pending` | Route B realtime 曾把 `vehicle_presence/car` 错写成“未佩戴安全帽”。现已在最终 Alarm JSON 写入点实现 `fact_guard.py`：不合规 LLM 文本保留 raw 审计，但发布文本替换为 detector-fact 模板，并记录 `json_fact_conflict` 与原因；本地正反例已通过，待 Jetson resident text 板端回放复验 |
| P05-JETSON-ROUTE-B-DUAL-SERVICE-V1-001 | 2026-07-14 | Jetson 8GB | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v1`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v2`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v3`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4`; `20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5`; `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1`; `20260716_jetson_8gb_alarm_service_route_b_target_v1`; `20260716_jetson_8gb_alarm_service_route_b_target_v2`; `20260717_jetson_8gb_alarm_service_route_b_target_v3`; `20260717_p05_dual_board_target_v1_jetson` | service / queue / async_vlm_worker | P1 | `target_pass_after_prewarm_postrun` | Route B dual-service 已完成 Jetson accepted `required`、单板 `target` 和双板 target 槽位；`target_v3` 已把 `postrun async VLM` 推到严格 `2/2 pass`，当前仅剩 Jetson text 语义约束 |
| P05-JETSON-ASYNC-VLM-WRAPPER-ENTRYPOINT-001 | 2026-07-14 | Jetson 8GB | `20260714_jetson_8gb_async_vlm_person_diag_v1`; `20260715_jetson_8gb_async_vlm_person_diag_run_v2` | wrapper / async_vlm_worker | P1 | `fixed_and_board_verified` | `run_jetson_p7_vlm_async_enrichment_smoke.sh` 一度错误调用 `run_alarm_service.py`，导致 async-only 诊断入口会错误创建当前 `RUN_ID` 的 service 输出并可能吞掉只读 `events_input` 语义；现已改为直接调用 `run_async_vlm_enrichment.py`，且 `run_v2` 已在板端打印 async 专用产物路径 |
| P05-JETSON-ASYNC-VLM-OUTPUT-ENCODING-V1-001 | 2026-07-14 | Jetson 8GB | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4`; `20260715_jetson_8gb_async_vlm_person_diag_run_v1`; `20260715_jetson_8gb_async_vlm_person_diag_run_v2` | async_vlm / display_chain | P2 | `closed_as_display_mojibake_false_positive` | 先前依据 shell paste / `Get-Content` 看到的“乱码”并非 JSONL 文件本身损坏；同一文件用 Python 按 `utf-8` 直接读取后，`vlm_summary` / `vlm_raw_output` 为正常中文，问题收口到宿主显示/同步链路 |
| P05-JETSON-RESIDENT-DETECTOR-CUDA-INIT-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v3` | detector / tensorrt / cuda | P1 | `open_pending_clean_rerun` | Jetson P7 v3 中 resident detector 在创建输出 JSONL 前即退出，detector log 记录 `NvMapMemAllocInternalTagged error 12` 与 `CUDA initialization failure with error: 2` |
| P05-JETSON-RESIDENT-CONCURRENCY-CUDA-CAPACITY-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v4`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v6` | resident concurrency / cuda capacity | P1 | `text_device_none_applied_but_vlm_startup_still_fails` | Jetson P6-VLM 已通过，但 P7 并发窗口中 resident VLM startup 仍失败；`v5` 的 text CLI 参数错误已修复，`v6` 证明失败层级重新回到 VLM startup |
| P05-JETSON-LLAMA-DEVICE-NONE-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v5` | llama.cpp / cli compatibility | P1 | `fixed_by_cpu_alias_to_none` | Jetson P7 v5 为了让 text resident 留在 CPU，传入 `--text-device cpu`，但当前 llama-server 版本不接受 `cpu`，只接受 `none`；已在 Project5 client 内兼容 `cpu -> none` |
| P05-JETSON-VLM-DEVICE-NONE-NEGATIVE-001 | 2026-07-14 | Jetson 8GB | `20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1`; `20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1` | llama.cpp / multimodal device routing | P1 | `negative_result_recorded_not_default` | `VLM_DEVICE=none` 已完成 standalone 与并发窗口对照实验；结果是 standalone P6 从可通过退化为首个请求 timeout，并发 P7 仍然两次 VLM timeout，且 detector FPS 降到 `21.425603` |
| P05-JETSON-RESIDENT-RUNTIME-BACKPRESSURE-001 | 2026-07-13 | Jetson 8GB | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v7`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` | resident runtime / queue / timeout | P1 | `queue_mitigation_verified_vlm_request_path_still_fails` | `v7` 暴露 queue backpressure；`v8` 已把 `drop_count` 收口到 0 并进入有效窗口，但 resident VLM request 仍失败 |
| P05-RK3588-VIDEO-DISABLED-001 | 2026-07-04 | RK3588 8GB | none_for_project5_video | video | P1 | `policy_frozen` | SmolVLM2 视频主线不进入项目五，必须使用检测/抽帧/ROI/text 摘要替代 |
| P05-RK3588-VLM-LATENCY-001 | 2026-07-04 | RK3588 8GB | project4 selected run | vlm | P2 | `policy_frozen` | Qwen3-VL RKNN/RKLLM p95 约 `57.2s`，只能低频异步 ROI/关键帧调用 |
| P05-RK3588-LLM-LOWFREQ-001 | 2026-07-04 | RK3588 8GB | project4 selected run | llm | P2 | `policy_frozen` | Qwen3-1.7B RKLLM p95 约 `26.63s`，不能写成强实时文本解释 |
| P05-RK3588-CONCURRENCY-PENDING-001 | 2026-07-04 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | system | P1 | `required_interface_schema_pass` | 项目四未覆盖 RKNN 检测 + RKLLM/Qwen3-VL 并行资源冲突；RK3588 已完成 30min detector/event/template/VLM stub/Alarm JSON/per-event/stability schema，真实 RKLLM/Qwen3-VL 仍需实测 |
| P05-RK3588-RESIDENT-DETECTOR-PARTIAL-JSON-001 | 2026-07-10 | RK3588 8GB | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v1` | service/detector tail | P1 | `fixed_by_tail_partial_line_guard` | 在线 tail `resident_detector.jsonl` 时读到了未换行半行 JSON，service 在 1 秒内退出；`p05_tail_guard_v2` 修复后 v2 复跑通过 |
| P05-RK3588-PROJECT3-SCHEMA-PLAYLIST-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_smoke_v1_project3_detector` | schema | P2 | `fixed_by_schema_allowed_set_update` | Project3 detector raw 已生成 18048 行，但板端旧 schema 不接受 `input_source_type=video_playlist`；更新 allowed set 后只重跑 schema check，状态 pass |
| P05-RK3588-ALARM-SCHEMA-PATH-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_smoke_v1` | schema | P2 | `fixed_by_correct_schema_path` | Alarm JSON 已生成 75 行，临时校验命令误用不存在的 `benchmark/schemas/alarm_output_schema.json`；改用 `projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json` 后 schema pass |
| P05-RK3588-RKLLM-OUTPUT-CLEANUP-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | llm | P2 | `fixed_by_rkllm_output_cleanup` | 首次 Project5 RKLLM 输出把 `I rkllm:` runtime banner 混入 `llm_explanation`；已在 `run_llm_explain.py --mode rkllm` 清洗 runtime 日志并复跑，rows=3 bad=0 contaminated=0 |
| P05-RK3588-ASTRA-CAMERA-SMOKE-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | camera/system | P2 | `camera_alarm_chain_smoke_pass_with_vlm_stub` | Astra S OpenNI 摄像头已跑通 detector/event/real RKLLM/Alarm JSON/per-event raw；VLM 仍为 route stub，未生成 Project5 stability raw |
| P05-REAL-VLM-ASSET-PENDING-001 | 2026-07-08 | RK3588 8GB | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` | vlm/assets | P1 | `fixed_by_asset_extraction_and_mt384_quality_regression` | 已用 `SAVE_OUTPUT_VIDEO=1` 和抽帧脚本补齐 3 个事件资产、5 张 ROI；真实 Qwen3-VL mt384 runtime rows=3 pass，bad=0，历史 128-token 截断已修复 |
| P05-RESIDENT-SERVICE-GAP-001 | 2026-07-08 | Jetson/RK3588 | all current Project5 runs | service/concurrency | P1 | `closed_by_publishable_text_guard_v3` | 当前 Project5 已证明 RK3588 单板 `P8/P9`、Jetson 单板 `P8/P9`、双板 `20260716_p05_dual_board_required_v1` 与双板 `20260717_p05_dual_board_target_v1`；`20260718...text_fact_guard_smoke_v3` 已验证 Jetson 原始文本冲突不会进入发布 Alarm JSON，主线验收收口 |
| P05-DUAL-BOARD-TARGET-OVERLAP-001 | 2026-07-18 | Jetson/RK3588 | `20260717_p05_dual_board_target_v1` | dual-board orchestration | P1 | `fixed_dual_board_target_ready` | 首次汇总读取的是旧 Jetson stability 文件版本，显示零重叠；同步当前原始记录后，Jetson `2026-07-18T11:07:02Z` 至 `13:07:20Z`，RK3588 `11:07:25Z` 至 `13:07:29Z`，启动差 `22.5s`、有效重叠 `7194.72s`，满足 target 所需 `>=6900s`，自动汇总为 `dual_board_target_ready`。修复方式是以当前原始 stability JSONL 重新生成组级汇总，不能继续采用旧 summary。 |

## 问题记录

### P05-JETSON-VIDEO-DISABLED-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-04 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` |
| 关联 run_id | `none_for_multiframe_video` |
| 模块 | video |
| 现象 | 项目四 SmolVLM2 多帧视频路线未形成可准入 selected run |
| 证据 | `projects/04_llm_vlm_independent/reports/project5_integration_decision.md`; `projects/04_llm_vlm_independent/reports/smolvlm2_video_benchmark.md` |
| 影响范围 | Jetson 项目五不能写成 SmolVLM2 短视频理解系统 |
| 根因 | Transformers CUDA route 被 CPU-only PyTorch 阻塞；GGUF 多帧 route 出现 context/media slot 不足 |
| 处理动作 | 禁用 video_vlm；使用检测/抽帧/ROI 摘要替代 |
| 回归要求 | alarm JSON 中 `fallback_status.video=disabled_by_project4_decision` |
| 当前状态 | `policy_frozen` |

### P05-JETSON-VLM-LATENCY-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-04 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` |
| 关联 run_id | `20260628_jetson_8gb_qwen3_vl_2b_q4_k_m_gguf_llamacpp_cuda_image_multi_input_formal_v2_mmproj_offload` |
| 模块 | vlm |
| 现象 | Qwen3-VL formal v2 p50 约 `24.12s`，p95 约 `33.11s` |
| 证据 | `projects/04_llm_vlm_independent/reports/qwen3_vl_2b_benchmark.md`; project4 decision |
| 影响范围 | 不允许逐帧运行，不允许同步阻塞检测 |
| 处理动作 | `async_roi_only_low_frequency`; max 2 events/min; timeout 45000 ms; timeout 时 skip VLM |
| 回归要求 | 项目五检测 FPS/p95 与项目三基线的 delta 必须可解释 |
| 当前状态 | `policy_frozen` |

### P05-JETSON-LLM-LOWFREQ-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-04 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` |
| 关联 run_id | `20260626_jetson_8gb_qwen3_1_7b_q4_k_m_gguf_llamacpp_cuda_text_ctx512_formal_v1` |
| 模块 | llm |
| 现象 | Qwen3-1.7B 文本 p95 约 `6.37s`，decode 约 `29.345 tok/s` |
| 证据 | `projects/04_llm_vlm_independent/reports/qwen3_1_7b_benchmark.md`; project4 decision |
| 影响范围 | 只能低频/异步解释，不能写成强实时主线 |
| 处理动作 | timeout 10000 ms；超时使用模板告警 JSON |
| 回归要求 | per-event raw 记录 `llm_total_ms`、timeout 和 fallback |
| 当前状态 | `policy_frozen` |

### P05-JETSON-CONCURRENCY-PENDING-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-04 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` |
| 关联 run_id | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` |
| 模块 | system |
| 现象 | 项目四未覆盖检测+LLM/VLM 并发资源冲突；Jetson 已补 30 分钟 required 后处理链路验证 |
| 影响范围 | 可以声明 Jetson required30min 后处理链路通过；不能声明完整并发常驻服务；RK3588 仍待执行 |
| 处理动作 | Jetson 已执行 10 分钟 smoke 和 30 分钟 required；RK3588 仍需按同一口径记录 per-event 和 time-window raw |
| 回归要求 | `alarm_system_benchmark.md`、`stability_report.md`、`failure_and_fallback.md` 全部回填 |
| 当前状态 | `jetson_required30min_pass_with_caveat` |

### P05-JETSON-SMOKE-STUB-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-04 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md` |
| 关联 run_id | `20260704_jetson_8gb_alarm_system_smoke_v1` |
| 模块 | system |
| 现象 | 项目五结构化链路已跑通：event package 542 行、alarm JSON 542 行、per-event raw 542 行，三项 schema 均 pass；但 LLM 为 template fallback，VLM 为 stub，未做真实 ROI/keyframe/clip 和项目五 monitor |
| raw result | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_alarm_system_benchmark.jsonl` |
| 日志路径 | `logs/runtime/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_*.log`; `logs/benchmark/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_alarm_system_benchmark.log` |
| 影响范围 | 该 run 只能证明结构化接口和 schema，不代表真实 LLM/VLM 或稳定性通过 |
| 处理动作 | 下一步替换真实 Qwen3-1.7B 文本调用，补项目五 monitor，再做 10 分钟 smoke 和 30 分钟 required |
| 当前状态 | `open_pending_real_model_run` |

### RK3588 项目四继承风险组

| issue_id | 证据 | 影响范围 | 处理动作 | 当前状态 |
|---|---|---|---|---|
| P05-RK3588-VIDEO-DISABLED-001 | `projects/04_llm_vlm_independent/reports/project5_integration_decision.md`; SmolVLM2 RK3588 诊断/失败记录 | RK3588 项目五不能写成 SmolVLM2 短视频理解系统 | 禁用 video_vlm；使用检测/抽帧/ROI/text 摘要替代 | `policy_frozen` |
| P05-RK3588-VLM-LATENCY-001 | `20260703_rk3588_8gb_qwen3_vl_2b_rknn_rkllm_image_cn_formal_v2_max512`，p95 `57199.9 ms` | 不允许逐帧运行，不允许同步阻塞检测 | `async_roi_only_low_frequency`; max 1 event/min; timeout 70000 ms; timeout 时 skip VLM | `policy_frozen` |
| P05-RK3588-LLM-LOWFREQ-001 | `20260701_rk3588_8gb_qwen3_1_7b_rkllm_text_ctx2048_formal_v2 + quality_v1 + quality_v2`，p95 `26628.865 ms` | 只能低频/异步解释，不能写成强实时文本主线 | timeout 30000 ms；超时使用模板告警 JSON | `policy_frozen` |
| P05-RK3588-CONCURRENCY-PENDING-001 | `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1`; `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | 不能声明 RK3588 完整并发真实模型验收通过 | required interface 已过，真实 RKLLM text smoke 已过；继续补真实 Qwen3-VL ROI 和可选完整并发稳定性 | `required_interface_plus_rkllm_text_smoke` |
| P05-REAL-VLM-ASSET-PENDING-001 | Project5 required/Astra event package 中 `keyframe_path=null`、`roi_paths=[]`；历史 mt128 多目标输出截断 | 不能把 route stub 或项目四独立 VLM p95 写成项目五真实 VLM | 已用 Project3 `SAVE_OUTPUT_VIDEO=1` 重跑可复现输入，执行 `extract_event_assets_from_video.py`，并以 `--max-tokens 384` 复跑 `run_vlm_roi_qa.py --mode rkllm_multimodal` | `fixed_by_asset_extraction_and_mt384_quality_regression` |

### P05-REAL-VLM-ASSET-PENDING-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-08 |
| board | RK3588 8GB |
| 关联 run_id | `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` |
| 模块 | vlm/assets |
| 现象 | 旧 required/Astra event package 只有 `roi_boxes`，无法直接输入 Qwen3-VL；新 run 开启 `SAVE_OUTPUT_VIDEO=1` 后可抽取关键帧和 ROI |
| 处理动作 | `extract_event_assets_from_video.py` 生成 `events_with_assets` rows=3，ROI images=5；`run_vlm_roi_qa.py --mode rkllm_multimodal` 调用 Qwen3-VL RKNN vision + RKLLM decoder |
| 回归结果 | event-assets schema pass；VLM mt384 rows=3、status=pass、bad=0、total_ms=`20172/28550/17747`、decode=`9.9667/8.6903/9.1223 tok/s` |
| caveat | 该 run 只证明真实 VLM runtime smoke，不证明 resident VLM 或检测/VLM 并发稳定性 |
| 当前状态 | `fixed_by_asset_extraction_and_mt384_quality_regression` |

### P05-RK3588-RKLLM-OUTPUT-CLEANUP-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-08 |
| board | RK3588 8GB |
| 关联 run_id | `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` |
| 模块 | llm |
| 现象 | RKLLM runtime 初始化日志和模型回答共同写入 stdout/stderr，首次 Project5 适配结果把 `I rkllm:`、`rkllm-runtime version`、`loading rkllm model` 混入 `llm_explanation` |
| 影响范围 | schema 可以通过，但 Alarm JSON 的解释文本会被运行时日志污染，不能作为最终告警解释质量证据 |
| 处理动作 | `run_llm_explain.py --mode rkllm` 增加 RKLLM runtime banner 清洗，并在清洗后再抽取最终解释；清洗后仍残留 runtime 日志时不判 `pass` |
| 回归结果 | 复跑后 `llm_rows=3`、`llm_bad_rows=0`、`llm_contaminated_rows=0`；首条 `total_ms=14804.1`、`decode_tokens_per_s=13.3427`；Alarm JSON/per-event schema pass |
| 当前状态 | `fixed_by_rkllm_output_cleanup` |

### P05-RK3588-RESIDENT-DETECTOR-PARTIAL-JSON-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-10 |
| board | RK3588 8GB |
| 关联 run_id | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v1` |
| 模块 | service / detector tail |
| 现象 | `p05_rk3588_p3_control.py run` 启动后约 1 秒退出，报 `resident_detector.jsonl:12: invalid JSON: Unterminated string` |
| 影响范围 | resident detector smoke 无法进入 10 分钟窗口，P3 不能判定通过 |
| 根因 | `detector_service.py` 在线 tail detector JSONL 时，对文件末尾“尚未写完且尚未换行”的半行 JSON 直接执行了解析 |
| 处理动作 | 在 `ResidentProcessDetectorService._tail_detector_output()` 中加入 partial-line guard：若当前行没有以换行结束且 detector 仍在运行，则回退文件指针并等待下一轮 |
| 回归结果 | 同步 `p05_tail_guard_v2` 后，`20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` 实际运行 `600.885s`，resident detector raw `18048` 行，event/alarm/per-event/stability 四类 schema 全部 pass，`drop_count=0` |
| 当前状态 | `fixed_by_tail_partial_line_guard` |

### P05-JETSON-RESIDENT-VLM-CUDA-OOM-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05A_Jetson_告警解释系统规范.md`; `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md` |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v2` |
| 模块 | llama.cpp resident VLM / concurrency |
| 现象 | 执行 `bash projects/05_alarm_system/scripts/service/run_jetson_p7_resident_service_smoke.sh` 时，service 在初始化 `llama_cpp_multimodal_resident` worker 阶段退出，Python 报错：`resident llama.cpp VLM server exited during startup: exit_code=1`。 |
| 直接证据 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v2_llama_cpp_vlm_runtime/llama_cpp_resident_vlm_server.log` |
| text 是否已启动 | 已启动。`logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v2_llama_cpp_text_runtime/llama_cpp_resident_text_server.log` 显示 Qwen3-1.7B text server 已成功 `model loaded` 并监听 `http://127.0.0.1:52849`。`run_alarm_service.py` 中 `ServiceTextWorker(...)` 构造先于 `ServiceVlmWorker(...)`，因此这次不是“只启动了 VLM”，而是“text 已起，VLM 启动失败”。 |
| VLM 模型 | `models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf` + `models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf` |
| 日志关键行 | `CUDA0 : Xavier (6833 MiB, 3471 MiB free)`；`[mtmd] estimated worst-case memory usage of mmproj is 1103.91 MiB`；`allocating 450.60 MiB on device 0: cudaMalloc failed: out of memory`；`unable to allocate CUDA0 buffer` |
| 影响范围 | Jetson resident VLM smoke、Jetson 单板 `resident_service_smoke` 和 `resident_service_required` 均不能按旧默认值继续验收。 |
| 根因判断 | 这是 CUDA 设备侧单次大块 buffer 申请失败，不是“系统 RAM 累加后总量不足”。关键证据是日志同时给出 `3471 MiB free`，但依旧无法完成 `cudaMalloc(450.60 MiB)`。在 Jetson 上这更接近“大块连续/可映射 device memory 不足”，并受 unified memory、NvMap 分配方式和碎片化影响。另一个旁证是 text server 启动时日志记录 `CUDA0 free=4061 MiB`，而 VLM 启动时只剩 `3471 MiB`，说明在 VLM 启动前已经有额外 GPU 可分配空间被占用。 |
| 已验证的非根因 | `--vlm-no-mmproj-offload` 已生效，因此不是 mmproj 仍强制上 GPU 的旧问题；`--vlm-no-kv-offload` 也已接入，但在当前 Jetson + llama.cpp 组合下仍不足以完全阻止 server 触碰 CUDA。 |
| 临时处理 | 已短暂尝试把 Jetson wrapper 收紧到显式 CPU-only，但按当前策略先回退该代码改动，优先执行板端重启后的原配置复测，以判断问题是否主要来自重启前的 device-side 内存碎片或大块可分配显存不足。 |
| 回归要求 | 先重启 Jetson，再按原配置重跑 Jetson `P6 resident VLM smoke`，随后重跑 Jetson `P7 resident concurrency smoke`。最低通过标准：1) VLM server 可成功启动；2) resident VLM rows 全部 `pass`；3) 同一 `resident_server_pid`；4) `resident_model_load_count=1`；5) P7 `window_requirement_met=true`。 |
| 重启后复测 1 | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v3` 已证明“startup OOM”不是唯一阻塞点：service log 记录 `server_pid=3090`、`model_load_count=1`，server log 记录 `CUDA0 : Xavier (6833 MiB, 5695 MiB free)`、`model loaded` 和监听 `http://127.0.0.1:36465`，说明 VLM server 已经成功启动。 |
| 重启后复测 1 失败点 | 同一条 `v3` server log 在首个图片请求阶段出现 `prompt processing`、`encoding mtmd batch`，随后被取消；`benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v3_vlm_outputs.jsonl` 中 3 条 VLM rows 全部 fallback，第 1 条错误为 `resident llama.cpp VLM request failed: timeout: timed out`，后两条为 `resident llama.cpp VLM server is not running`。 |
| 结论更新 | 该问题目前已从“VLM 启动即 OOM”扩展为“两段式阻塞”：旧并发配置下会出现 startup OOM；重启后 standalone P6-VLM 虽然能启动，但首个多模态请求仍会超时。两者都必须记录，不能再把 Jetson 阻塞点简化成单一 OOM。 |
| 当前状态 | `startup_oom_reproduced_request_timeout_after_reboot` |

### P05-JETSON-RESIDENT-VLM-REQUEST-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md` |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v3`; `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` |
| 模块 | llama.cpp resident VLM / request path |
| 现象 | 该问题现在分成前后两段：`v3` 时 standalone P6-VLM wrapper 已启动 resident server，但 `vlm_rows=3`、`vlm_bad_rows=3`，3 条事件全部退化为 fallback；`v4` 经过更保守参数收口后，standalone resident VLM 已通过，`vlm_bad_rows=0`；但 `v8` 并发窗口中两次真实 resident VLM 请求又分别报 `RemoteDisconnected` 和 `timeout`。 |
| 直接证据 | `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v3_vlm_outputs.jsonl`; `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4_vlm_outputs.jsonl`; `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8_vlm_outputs.jsonl`; `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8_llama_cpp_vlm_runtime/llama_cpp_resident_vlm_server.log` |
| 模型 | `qwen3-vl-2b-instruct-q4_k_m.gguf` + `qwen3-vl-2b-instruct-mmproj-f16.gguf` |
| 根因判断 | 当前问题已不再是“模型起不来”，而是 Jetson 上多模态真实 request path 在并发服务环境中仍不稳定。`v8` 的 VLM runtime log 证明 server 已成功启动并监听，首个请求也已进入 `prompt processing` 与 `encoding mtmd batch`，最终却被取消并映射为 `RemoteDisconnected`/`timeout`。 |
| 当前处理 | Project5 已把 `run_jetson_p6_resident_vlm_smoke.sh` 默认值进一步收紧到 CPU-first：`VLM_CTX=1536`、`VLM_MAX_TOKENS=96`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、`VLM_IMAGE_MIN/MAX_TOKENS=512`，并保留 `VLM_REQUEST_RETRIES=1`；P7/P8 又继续固定 `DETECTOR_START_ORDER=after_workers`、`SERVICE_QUEUE_CAPACITY=192` 与更小的 text/VLM token budget，用来把 request 失败和 queue/backpressure 分层暴露。 |
| 回归要求 | 下一轮并发复测至少满足：1) `vlm_pass_rows=2`；2) 两次真实请求保持同一 `resident_server_pid`、`resident_model_load_count=1`；3) `drop_count=0`；4) VLM raw 不再出现 `RemoteDisconnected` 或 `timeout`。 |
| 当前状态 | `standalone_pass_but_route_a_and_async_request_failures_reproduced` |

2026-07-14 新证据补充：

- `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` 已把 resident text 从链路中移除，仅保留 `resident detector + resident VLM + template text`。结果是 `window_requirement_met=true`、`event_count=136`、`alarm_count=136`、`llm_call_count=0`、`vlm_call_count=2`、`drop_count=0`，但两次真实图片请求都退化为 `llama_cpp_multimodal_resident_request_failed_stub_fallback`，错误统一为 `timeout: timed out`。
- `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 又把 VLM 拆到第二条 service run，只消费 Route B 的 `events.jsonl` 和回放资产。结果仍然是 `vlm_call_count=2`、`vlm_pass_rows=0`、`vlm_bad_rows=2`，两次真实图片请求继续 timeout。
- `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v2` 则把这个判断再往前收紧一步：双进程 Route B 中 realtime lane 已恢复 `event_count=136`、`alarm_count=136`、`drop_count=0`，而 async VLM worker 也已不再在首条后崩溃，`async_vlm_rows=2`、`async_vlm_model_calls=2`。这意味着 B 方案编排与异步 worker 生命周期已经成立，剩余失败继续集中在 Jetson multimodal startup/request path 本身。
- 这两条新 run 共同说明：Jetson 当前 resident VLM 的核心问题不再能归因于 resident text 干扰，也不是 queue backpressure。即使把 resident text 从实时链路里完全拿掉，multimodal request path 仍然失败。

| 2026-07-14 结论更新 | 内容 |
|---|---|
| Route A 结果 | 有效时间窗成立，但 live detector 下 resident VLM 两次真实请求均 timeout |
| Route B async 结果 | 脱离 realtime text 链路后，两次真实 VLM 请求仍 timeout |
| Route B dual-service v2 结果 | realtime lane 和 async worker 生命周期都已成立，但两次 `llama_cpp_multimodal_once` 真实调用分别报 `exit_code=-11` 和 `RemoteDisconnected` |
| 当前根因边界 | Jetson multimodal request path 本身尚未收口 |
| 当前状态 | `standalone_pass_but_route_a_and_async_request_failures_reproduced` |

### P05-JETSON-ROUTE-B-DUAL-SERVICE-V1-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-14 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v1`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v2`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v3`; `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4`; `20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5`; `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1` |
| 模块 | Route B dual-service / queue / async VLM worker |
| `v1` 现象 | 首轮双进程 Route B 中，realtime lane 虽达到 `window_requirement_met=true`，但出现 `event_count=136`、`alarm_count=132`、`drop_count=4`；同时 async worker 只产出 `async_vlm_rows=1` 就退出。 |
| `v1` 直接证据 | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v1_async_vlm_stdout.log` 报 `AttributeError: 'str' object has no attribute 'open'`，定位到 `run_async_vlm_enrichment.py` 的 `rebuild_outputs()` 在读取 `llm_input` 时把字符串直接传给了 `read_jsonl()`。 |
| 根因判断 | 这是两层问题叠加：1) async worker 的 `llm_input` 路径类型 bug 导致首条处理后崩溃；2) realtime lane 的 `SERVICE_QUEUE_CAPACITY=32` 对 Jetson 这条 detector+text 路线偏紧，导致 `alarm_count` 小于 `event_count` 且 `drop_count=4`。 |
| 修复动作 | 1) `run_async_vlm_enrichment.py` 先把 `args.llm_input` 归一化为 `Path` 再传给 `read_jsonl()`；2) `run_jetson_p7_detector_text_resident_smoke.sh` 默认 `SERVICE_QUEUE_CAPACITY` 提高到 `64`；3) Jetson Route B realtime 验收脚本新增 `drop_count != 0` 直接失败；4) `vlm_worker.py` 补齐 `llama_cpp_multimodal_once` 对 `--vlm-request-retries` 的真实消费，Route B dual-service 默认 `VLM_REQUEST_RETRIES=1`。 |
| `v2` 回归结果 | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v2` 已给出 `window_sec=622.899`、`detection_fps=28.9742`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`drop_count=0`；async worker 侧已达到 `async_vlm_rows=2`、`async_vlm_model_calls=2`、不再首条后崩溃。 |
| `v3` 再回归结果 | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v3` 进一步给出 `window_sec=646.611`、`detection_fps=27.907041`、`event_count=136`、`alarm_count=136`、`drop_count=0`、`restart_count=1`；async worker 达到 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`。pass 行对应 `vehicle_presence_candidate_000001_frame_2`，其 `runtime_log_path` 已落到 `_retry1.log` 且 `resident_retry_count=1`，证明 once 模式的第二次尝试成功返回了真实 VLM 输出。 |
| `v4` 最新结果 | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4` 给出 `window_sec=627.353`、`detection_fps=28.741394`、`event_count=136`、`alarm_count=136`、`drop_count=0`、`restart_count=0`；async worker 仍为 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`。但这次 pass 行 `resident_retry_count=0`、`resident_server_pid=503522`、`resident_model_load_count=1`、`resident_request_index=1`、`vlm_total_ms=229011.465`，说明真实 pass 不再依赖 retry1；fallback 行仍为 `person_presence_candidate_000000_frame_2`，错误从单纯 `timeout` 收口为 `RemoteDisconnected: Remote end closed connection without response`，且 `once_attempts=2`。 |
| `v5` 严格门槛结果 | `20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5` 首次启用 `ASYNC_VLM_REQUIRE_PASS_ROWS=2`。realtime lane 继续稳定：`window_sec=649.994`、`detection_fps=27.76641`、`event_count=136`、`alarm_count=136`、`drop_count=0`、`llm_pass_rows=2`、`llm_resident_server_pids=[709936]`、`llm_resident_model_load_counts=[1]`。async lane 仍为 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`，因此脚本按新门槛直接失败并打印 `Route B dual-service async VLM failed: pass_rows=1 < required=2`。失败事件仍为 `person_presence_candidate_000000_frame_2`，错误为 `RemoteDisconnected`，且 `once_attempts=2`；成功事件仍为 `vehicle_presence_candidate_000001_frame_2`，这次 pass 回到 `_retry1.log`，`resident_retry_count=1`、`vlm_total_ms=220489.768`。 |
| `v5` person 单事件对照 | 随后用户把 `v5` 中失败的 `person_presence_candidate_000000_frame_2` 单独抽出，执行 `20260715_jetson_8gb_async_vlm_person_from_v5_run_v1` async-only 诊断。结果为 `async_vlm_rows=1`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=0`、`vlm_total_ms=154961.29`、`resident_retry_count=0`。这证明同一 person 事件在脱离 Route B 并发窗口后可以正常通过。 |
| `postrun_v1` 对照结果 | `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1` 将同一条 Route B wrapper 切换到 `ASYNC_LAUNCH_MODE=postrun`。结果为 realtime lane `window_sec=617.063`、`window_requirement_met=true`、`detection_fps=29.248229`、`event_count=136`、`alarm_count=136`、`drop_count=0`、`llm_pass_rows=2`、同一 `llm_resident_server_pids=[753178]`、`llm_resident_model_load_counts=[1]`；async lane `async_vlm_rows=2`、`async_vlm_pass_rows=2`、`async_vlm_fallback_rows=0`、`async_vlm_failed_rows=0`、`async_vlm_blocked_rows=0`，最终脚本打印 `JETSON_ROUTE_B_DUAL_SERVICE_RESULT=realtime_detector_text_plus_async_vlm_worker_ready`。 |
| `required_v1` 正式结果 | `20260715_jetson_8gb_alarm_service_route_b_required_v1` 已沿同一 accepted 拓扑完成 30 分钟 required。realtime lane 给出 `window_sec=1818.786`、`requested_window_sec=1800.0`、`window_requirement_met=true`、`stability_tier=required`、`detection_fps=29.76161`、`event_count=397`、`alarm_count=397`、`drop_count=0`、`llm_call_count=2`、`llm_rows=397`、`llm_pass_rows=2`、同一 `llm_resident_server_pids=[789848]`、`llm_resident_model_load_counts=[1]`；async lane 给出 `async_vlm_rows=2`、`async_vlm_pass_rows=2`、`async_vlm_fallback_rows=0`、`async_vlm_failed_rows=0`、`async_vlm_blocked_rows=0`，最终脚本打印 `JETSON_P8_ROUTE_B_REQUIRED_RESULT=realtime_detector_text_plus_postrun_async_vlm_required_ready`。 |
| `target_v1` 最新结果 | `20260716_jetson_8gb_alarm_service_route_b_target_v1` 已证明 accepted Route B 的 realtime lane 可以稳定跑满 2 小时：`window_sec=7243.821`、`requested_window_sec=7200.0`、`window_requirement_met=true`、`stability_tier=target`、`detection_fps=29.89044`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`、`llm_rows=1550`、`llm_pass_rows=2`、同一 `llm_resident_server_pids=[1069806]`、`llm_resident_model_load_counts=[1]`。但 async lane 只有 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`；fallback 事件为 `person_presence_candidate_000000_frame_2`，错误收口为 `RemoteDisconnected: Remote end closed connection without response`，脚本最终按严格门槛失败并打印 `Route B dual-service async VLM failed: pass_rows=1 < required=2`。 |
| `target_v1` 运行时证据补充 | `benchmark/raw/05_alarm_system/jetson_8gb/20260716_jetson_8gb_alarm_service_route_b_target_v1_async_vlm_outputs.jsonl` 与 `logs/runtime/05_alarm_system/jetson_8gb/20260716_jetson_8gb_alarm_service_route_b_target_v1_async_vlm_runtime/20260716_jetson_8gb_alarm_service_route_b_target_v1_person_presence_candidate_000000_frame_2.log` 进一步证明：失败不是纯业务超时。首个 async once 请求在 `llama-server` 首次多模态 decode 阶段直接报 `NvMapMemAllocInternalTagged ... error 12`、`CUBLAS_STATUS_NOT_INITIALIZED`；同一 async lane 的第 2 个 `vehicle_presence` 事件随后又在 `resident_retry_count=0` 下正常 pass。换句话说，Jetson target 当前主要缺口是“detector 刚退出后的首个 async once VLM 请求窗口”不稳定，而不是 accepted realtime lane 本身失效。 |
| `target_v2` 最新结果 | `20260716_jetson_8gb_alarm_service_route_b_target_v2` 已把 `ASYNC_POSTRUN_COOLDOWN_SEC=30` 与 `VLM_RETRY_BACKOFF_SEC=30` 带进正式 target wrapper。realtime lane 更稳：`window_sec=7219.181`、`requested_window_sec=7200.0`、`window_requirement_met=true`、`stability_tier=target`、`detection_fps=29.992737`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`、`event_queue_depth=30`、`llm_rows=1550`、`llm_pass_rows=2`、同一 `llm_resident_server_pids=[1315542]`、`llm_resident_model_load_counts=[1]`。但 async lane 仍停在 `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`，脚本依旧按严格门槛失败。 |
| `target_v2` 运行时证据补充 | `logs/runtime/05_alarm_system/jetson_8gb/20260716_jetson_8gb_alarm_service_route_b_target_v2_async_vlm_service.log` 显示 cooldown 与 retry backoff 已生效，但 `person_presence_candidate_000000_frame_2` 的 runtime log 仍再次落到同一 CUDA 初始化失败点：`NvMapMemAllocInternalTagged ... error 12`、`CUBLAS_STATUS_NOT_INITIALIZED`。与此同时，第 2 个 `vehicle_presence` 事件继续以 `resident_retry_count=0` 直接 pass，`vlm_total_ms=151933.815`。这说明单纯“detector 结束后多等 30 秒”还不足以消除 Jetson 上的首个 multimodal once 请求抖动。 |
| 新增收口动作 | Project5 现继续前推一层：1) `run_async_vlm_enrichment.py` / `vlm_worker.py` 新增 `--vlm-once-prewarm-request` 与 `--vlm-once-prewarm-max-tokens`，可在正式事件前执行一个不计入结果的首请求预热；2) `run_jetson_p9_route_b_postrun_target.sh` 现默认 `VLM_ONCE_PREWARM_REQUEST=1`、`VLM_ONCE_PREWARM_MAX_TOKENS=8`。下一轮 Jetson P9 应优先验证 `target_v3` 是否能把当前“首个真实请求死、第二个请求过”的模式推到严格 `2/2 pass`。 |
| 新增收口动作 | Project5 已新增两级缓冲旋钮：1) `run_jetson_p7_route_b_dual_service_smoke.sh` / `run_async_vlm_enrichment.py` 现支持 `VLM_RETRY_BACKOFF_SEC`，让 `llama_cpp_multimodal_once` 的 retry1 不再零间隔紧贴首次失败；2) `run_jetson_p9_route_b_postrun_target.sh` 现默认 `ASYNC_POSTRUN_COOLDOWN_SEC=30` 与 `VLM_RETRY_BACKOFF_SEC=30`，先给 detector/TensorRT 释放 CUDA 资源，再启动 postrun async VLM。下一轮 Jetson P9 应优先验证这两个新增缓冲是否能把 target 从 `1/2 pass` 推到 `2/2 pass`。 |
| `target_v3` 正式结果 | `20260717_jetson_8gb_alarm_service_route_b_target_v3` 已完成 Jetson accepted Route B 单板 2 小时 target：realtime lane `window_sec=7220.025`、`requested_window_sec=7200.0`、`window_requirement_met=true`、`detection_fps=29.989231`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`、`llm_rows=1550`、`llm_pass_rows=2`、同一 `llm_resident_server_pids=[1583009]`、`llm_resident_model_load_counts=[1]`；postrun async lane 给出 `async_vlm_rows=2`、`async_vlm_pass_rows=2`、`async_vlm_fallback_rows=0`、`async_vlm_failed_rows=0`、`async_vlm_blocked_rows=0`。 |
| `target_v3` 修复验证 | `logs/runtime/05_alarm_system/jetson_8gb/20260717_jetson_8gb_alarm_service_route_b_target_v3_async_vlm_service.log` 已记录 `request_retry_backoff_sec=30.0`、`once_prewarm_request=True`、`once_prewarm_max_tokens=8`，并最终打印 `async_vlm_stop processed_rows=2 pass_rows=2 bad_rows=0 model_calls=2 fallback_count=0`。这说明 Jetson accepted target 的真正收口组合不是单纯 cooldown/backoff，而是 `cooldown + retry backoff + once prewarm`。 |
| run_id 字段修复验证 | `20260715_..._v5_alarm_enriched_benchmark.jsonl` 现已写出当前 `run_id=20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5`，不再错误继承源事件旧 run_id。 |
| 新的保守调优 | Jetson async-only 入口与 Route B dual-service 现已把默认 `VLM_TIMEOUT_MS` / `VLM_STARTUP_TIMEOUT_MS` 从 `180000` 上调到 `240000`；该调整只作用于低频 async enrichment，不改 realtime detector+text 主链路参数。 |
| schema 证据 | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_async_alarm_schema_check.md`、`20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_async_benchmark_schema_check.md`、`20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_resident_stability_schema_check.md` 均为 `status: pass`。 |
| 现阶段结论 | Route B dual-service 的编排和异步 worker 生命周期已经成立；`v5` 证明 `parallel` 同窗拓扑在严格 `2/2 pass` 门槛下仍会停留在 `1/2 pass`，`postrun_v1` 证明同一套实时 detector+text 主链路配合同一 `RUN_ID` 下的 postrun async VLM 可以稳定做到 `2/2 pass`，`required_v1` 把这条 accepted 路线推进到 30 分钟 required，而 `target_v3` 最终把单板 2 小时 target 也闭环。`20260717_p05_dual_board_target_v1` 已完成有效重叠 `7194.72s` 的双板 target；随后 P6 v3 证明原始 text 漂移被发布侧事实守卫可靠隔离。 |
| 当前状态 | `dual_board_target_pass_postrun_async_vlm_2of2_publishable_text_guard_pass` |

### P05-JETSON-ASYNC-VLM-WRAPPER-ENTRYPOINT-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-14 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260714_jetson_8gb_async_vlm_person_diag_v1` 及后续手工 replay 诊断 |
| 模块 | async wrapper / entrypoint routing |
| 现象 | 手工运行 `run_jetson_p7_vlm_async_enrichment_smoke.sh` 时，脚本表面输出 `events=0 alarms=0 benchmark_rows=0`，与输入 `EVENTS_INPUT` 已有事件不符。 |
| 直接证据 | wrapper 当时仍在调用 `projects/05_alarm_system/scripts/service/run_alarm_service.py --detector-mode events_input`，而不是直接调用 `run_async_vlm_enrichment.py`。 |
| 根因判断 | 这是入口接错层级的问题，不是 VLM 模型本身失败。async-only 诊断入口应该把 `EVENTS_INPUT` 当作只读事件源，而不是再起一条完整 service replay。 |
| 修复动作 | `run_jetson_p7_vlm_async_enrichment_smoke.sh` 已改为直接调用 `projects/05_alarm_system/scripts/service/run_async_vlm_enrichment.py`，并统一输出 async 专用产物：`*_async_vlm_outputs.jsonl`、`*_alarm_enriched.jsonl`、`*_alarm_enriched_benchmark.jsonl`、`*_async_vlm_summary.md`。同时不再为该入口伪造新的 `events.jsonl` 或 `alarm_system_stability.jsonl`。 |
| 2026-07-15 新证据 1 | 用户板端回传的 `20260715_jetson_8gb_async_vlm_person_diag_run_v1` 已经拿到 `vlm_call_count=1`、`vlm_pass_rows=1`、`vlm_total_ms=157961.52` 的真实单事件 pass，但输出仍是旧 wrapper 风格的 `events=/llm=/vlm=/alarms=/benchmark=/stability=`，而不是新的 `async_vlm_output=/async_alarm_output=/async_benchmark_output=`。这说明板端当时实际运行的仍是旧版脚本，不应把该 run 记作“新 wrapper 直连 async worker”证据。 |
| 2026-07-15 新证据 2 | 用户随后回传的 `20260715_jetson_8gb_async_vlm_person_diag_run_v2` 已出现 `async_entrypoint=run_async_vlm_enrichment.py`、`async_vlm_output=...`、`async_alarm_output=...`、`async_benchmark_output=...`，并给出 `async_vlm_rows=1`、`async_vlm_pass_rows=1`、`async_alarm_rows=1`、`async_benchmark_rows=1`。这证明新 wrapper 已经真实同步到 Jetson 板端。 |
| 新的验收口径 | 这条入口现在只校验三类 async 产物：1) VLM 输出行；2) enriched alarm JSON schema；3) enriched benchmark schema。它不再声称自己是一个新的实时窗口 run。 |
| 回归要求 | 1) `async_vlm_rows > 0`；2) `async_alarm_rows == async_vlm_rows`；3) `async_benchmark_rows == async_vlm_rows`；4) 不得再出现“已有 source events，但 wrapper 输出 events=0 alarms=0”的自相矛盾现象。 |
| 当前状态 | `fixed_and_board_verified` |

### P05-JETSON-ASYNC-VLM-OUTPUT-ENCODING-V1-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-14 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4`; `20260715_jetson_8gb_async_vlm_person_diag_run_v1` |
| 模块 | async VLM output / display chain |
| 初始现象 | Route B dual-service `v4` 与 `20260715_jetson_8gb_async_vlm_person_diag_run_v1` 的同步文本里，`vlm_summary` 和 `vlm_raw_output` 看起来像乱码中文，例如 `杞﹁締鍦ㄥ浘鍍忎腑...` 或 `ROI/鍏抽敭甯у彲瑙佽瘉鎹細...`。 |
| 复核证据 | 对同一批 JSONL 文件直接使用 Python 按 `utf-8` 读取后，`20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_async_vlm_outputs.jsonl` 的 pass 行可正常得到“车辆在图像中可见……”；`20260715_jetson_8gb_async_vlm_person_diag_run_v2_async_vlm_outputs.jsonl` 可正常得到“ROI/关键帧可见证据：图像中可见一个穿着橙色上衣和蓝色裤子的人……”。 |
| 结论 | 当前没有证据表明 JSONL 文件本身发生编码损坏。更符合现有证据的解释是：宿主侧 shell paste、`Get-Content` 或同步展示链路把 UTF-8 正文错误显示成了 mojibake。 |
| 影响范围 | 不再把该问题计为“模型输出质量失败”或“业务文本不可用”的主阻塞项；但后续如需人工验收中文内容，必须优先使用 `python3/json` 或支持 UTF-8 的编辑器读取，而不要只看同步后的 shell paste。 |
| 当前处理 | 关闭该问题，保留它作为“显示层误判”的记录，避免后续再次把展示乱码误报成模型乱码。 |
| 回归要求 | 后续所有 Jetson async VLM 文本验收都以“Python `utf-8` 直读文件结果”为准；若再次出现只在同步文本中乱码、直读文件正常的情况，不再新建模型问题。 |
| 当前状态 | `closed_as_display_mojibake_false_positive` |

### P05-JETSON-RESIDENT-TEXT-FACT-DRIFT-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-14 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` |
| 模块 | llama.cpp resident text / semantic quality |
| 现象 | Route B realtime 的 runtime 指标已经通过：`window_sec=612.872`、`detection_fps=29.448237`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`，且同一 `resident_server_pid=343498`、`resident_model_load_count=1`、请求序号 `1/2` 递增；但第 2 条真实文本解释把 `vehicle_presence/car` 错写成了“未佩戴安全帽”。 |
| 直接证据 | `benchmark/raw/05_alarm_system/jetson_8gb/events/20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1_events.jsonl`; `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1_llm_outputs.jsonl` |
| 事件事实 | 第 2 条事件 `event_id=20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1_vehicle_presence_candidate_000001_frame_2` 的 `alarm_type=vehicle_presence`，检测事实为 `class_name=car`、`confidence=0.754915`、对应 bbox 为 `[67.938, 357.75, 207.562, 426.25]`。 |
| 错误输出 | 同一事件的真实 `llm_explanation` 为：`1) 未佩戴安全帽；2) 中等；3) 立即佩戴安全帽；4) 仅限于检测到的人员。` |
| 根因判断 | 当前 Jetson Route B 的 runtime 收口使用了更小的 text token budget 和更紧的输出约束，但缺少“事件事实白名单约束”和输出后验校验。结果是 resident text 运行时可以通过，却已经出现跨任务语义漂移。 |
| 影响范围 | 该问题不会影响 detector、event queue、resident server 复用和 Alarm JSON 写出，但会直接影响项目五“告警解释”业务可信度。因此 Route B 当前只能声明 realtime runtime pass，不能直接声明 explanation semantic pass。 |
| 当前处理 | 先把该问题独立记入问题库，避免被 resident VLM timeout 掩盖；下一步需要补 prompt 收紧、字段白名单约束、以及输出后验 fact-check。 |
| 回归要求 | 1) 真实文本解释不得引入 event package 之外的新目标、新属性或新风险类型；2) 至少对 `alarm_type`、`class_name`、`confidence`、`bbox` 和动作建议做规则后验校验；3) Route B 重新抽检时，`vehicle_presence` 不得再出现安全帽、跌倒、火焰等无关语义。 |
| 当前状态 | `runtime_pass_but_semantic_guard_missing` |

### P05-JETSON-VLM-DEVICE-NONE-NEGATIVE-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-14 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md` |
| 关联 run_id | `20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1`; `20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1` |
| 模块 | llama.cpp resident VLM / device routing |
| 现象 | 在 Jetson 上把 multimodal resident server 显式固定到 `VLM_DEVICE=none` 后，standalone P6 与并发 P7 都没有变好：P6 `vlm_rows=3`、`vlm_bad_rows=3`；P7 `vlm_call_count=2` 但 `vlm_pass_rows=0`、两次真实 VLM 请求都 timeout。 |
| standalone 直接证据 | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1_vlm_outputs.jsonl` 中前两条事件均为 `llama_cpp_multimodal_resident_request_failed_stub_fallback`，`metrics_error` 为 `resident llama.cpp VLM request failed: timeout: timed out`；第三条因 `max_calls` 用尽而 `not_executed`。 |
| standalone server log 证据 | `logs/runtime/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1_llama_cpp_vlm_runtime/llama_cpp_resident_vlm_server.log` 显示 server 成功 `model loaded` 并监听本地端口，但首个请求在 `prompt processing` 和 `encoding mtmd batch` 后被取消，最终没有产出可用回答。 |
| 并发窗口直接证据 | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1_vlm_outputs.jsonl` 中两条真实 VLM 调用都退化为 `llama_cpp_multimodal_resident_request_failed_stub_fallback`，错误相同：`resident llama.cpp VLM request failed: timeout: timed out`。 |
| 并发窗口系统指标 | `20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1` 虽然达到 `window_sec=842.31`、`window_requirement_met=true`、`drop_count=0`，但 `detection_fps` 降到 `21.425603`，`event_queue_depth=134`，明显劣于 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 的 `28.632848 FPS`。 |
| 根因判断 | 这说明问题不是“只要把 VLM 固定到 CPU/none device 就能解决 GPU 争用”这么简单。`VLM_DEVICE=none` 改变了 failure mode，但没有把 multimodal request path 变成 pass，反而让整体窗口更慢，表明 Jetson 当前瓶颈更接近 llama.cpp multimodal request path 本身，而不是单纯的 device 自动选择。 |
| 工程结论 | `VLM_DEVICE=none` 只能作为诊断开关保留，不能升级为 Jetson P6/P7/P8 默认值，也不能作为 Jetson resident_service 主线收口方案。Jetson 当前主线仍应保持：`detector resident + text resident` 为实时链路，VLM 仅作为低频异步 enrichment，或改做 `detector resident + VLM resident`、text 退回 template/rule 的另一条结构性路线。 |
| 回归要求 | 后续 Jetson 如果继续验证 VLM，不应再默认携带 `VLM_DEVICE=none`；除非明确做 device 路由对照实验。新的通过口径仍是：1) `vlm_pass_rows>=2`；2) `resident_server_pid` 与 `model_load_count=1` 可复用；3) `detection_fps` 不显著劣化；4) `drop_count=0`。 |
| 当前状态 | `negative_result_recorded_not_default` |

### P05-JETSON-RESIDENT-DETECTOR-CUDA-INIT-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v3` |
| 模块 | resident detector / TensorRT / CUDA |
| 现象 | 执行 `bash projects/05_alarm_system/scripts/service/run_jetson_p7_resident_service_smoke.sh` 时，service 直接报 `resident detector exited before creating output`，尚未进入真实 VLM 请求阶段。 |
| 直接证据 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v3_resident_detector.log`；`logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v3_service_stdout.log` |
| 日志关键行 | `NvMapMemAllocInternalTagged: 1074810371 error 12`；`[TensorRT] CUDA initialization failure with error: 2`；`BACKEND_RUNTIME_FAILED: failed to initialize tensorrt worker=0 core_mask=auto` |
| 影响范围 | 当前这轮 P7 v3 不能用于判断 Jetson resident text/VLM 并发是否通过，因为 detector 在写出首个 JSONL 之前就已经失败。 |
| 根因判断 | 这是 detector 侧 CUDA/TensorRT 初始化失败，不是 `run_alarm_service.py` 里的 VLM 请求 timeout。若板端已经同步到最新 Project5 代码，则 service 会先启动 detector、等待 detector JSONL 就绪，再初始化 text/VLM worker；因此当前失败应优先按 detector 冷启动资源问题处理，而不是继续归因到 VLM startup OOM。 |
| 临时处理 | 复测前必须先确认板端已同步最新 `run_alarm_service.py` 与 `detector_service.py`，并确保没有残留 `llama-server`/detector 进程占用 CUDA；必要时重启后直接先跑 P7，而不是先跑 P6 再跑 P7。 |
| 回归要求 | 1) `resident_detector.jsonl` 成功创建；2) `service_start` 后 detector 先就绪；3) `window_requirement_met=true`；4) detector、text、VLM 的失败需在同一 run 内分层可见。 |
| 当前状态 | `open_pending_clean_rerun` |

### P05-JETSON-RESIDENT-CONCURRENCY-CUDA-CAPACITY-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 spec | `projects/05_alarm_system/specs/05I_Jetson_正式执行流程.md`; `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v4`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v6` |
| 模块 | resident concurrency / text + VLM / CUDA 容量 |
| 现象 | 同一块 Jetson 上，`P6 resident VLM smoke v4` 已通过，但 `P7 resident detector + resident text + resident VLM` 在初始化 VLM worker 阶段再次失败，Python 报错 `resident llama.cpp VLM server exited during startup: exit_code=-11`。 |
| 已通过的前置证据 | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已拿到 `vlm_bad_rows=0`、`resident_server_pids=[4611]`、`resident_model_load_counts=[1]`、`resident_request_indexes=[1,2,3]`。因此 Qwen3-VL resident VLM 在 Jetson 单独运行时已经成立，当前失败不是“VLM 自身永远起不来”。 |
| 直接证据 1 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v4_llama_cpp_text_runtime/llama_cpp_resident_text_server.log`：text resident 启动时记录 `CUDA0 ... 4141 MiB free`，随后 `model loaded`、`server is listening`。 |
| 直接证据 2 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v4_llama_cpp_vlm_runtime/llama_cpp_resident_vlm_server.log`：VLM 启动时只剩 `CUDA0 ... 3506 MiB free`，随后出现 `[mtmd] estimated worst-case memory usage of mmproj is 1103.91 MiB`、`allocating 71.51 MiB on device 0: cudaMalloc failed: out of memory`、`failed to allocate compute buffers`。 |
| 直接证据 3 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v4_service_stdout.log`：Python 栈显示失败发生在 `ServiceVlmWorker(...).resident_client.start()` 阶段，而不是 detector 或首个 request 阶段。 |
| 关键判断 | 这次不是 `P6-v3` 那种“server 已启动，首个图片请求 timeout”；也不是 `P7-v3` 那种 detector/TensorRT 初始化失败。当前失败是第三种情况：`text resident` 已成功启动且仍占用一部分 CUDA 侧资源，导致 `VLM resident` 在 startup 阶段无法再完成 compute buffer 分配。 |
| 为什么 `TEXT_NGL=0` 还不够 | `TEXT_NGL=0` 与 `TEXT_NO_KV_OFFLOAD=1` 只能限制大模型层和 KV cache 的 GPU 使用，但 `llama.cpp` text resident 在默认 `device=auto` 下仍会探测并使用 CUDA backend。日志里 text server 明确打印了 `CUDA0`，这说明它并没有被强制留在 CPU。 |
| 根因 | Jetson 当前并发配置下，`resident text` 和 `resident VLM` 同时选择 `device=auto`，text worker 先占用 CUDA backend，VLM worker 再启动时剩余可分配 GPU/NvMap 空间不足，最终在 VLM startup 阶段 OOM 并触发 `exit_code=-11`。 |
| 处理过程 | 第一步先把 standalone VLM 收口到 pass，证明 VLM 本身可用；第二步对比 P7 v4 的 text/VLM runtime log，确认自由显存从 `4141 MiB` 下降到 `3506 MiB`；第三步回看 Project5 wrapper，确认此前只设置了 `TEXT_NGL=0` / `TEXT_NO_KV_OFFLOAD=1`，但没有显式把 text resident 固定到 CPU-only 设备；第四步把 Jetson `P7/P8` wrapper 默认值补成 `TEXT_DEVICE=none` 并透传到 `run_alarm_service.py`，同时在 resident client 中兼容历史 `cpu` 写法。 |
| 已落地修复 | `projects/05_alarm_system/scripts/service/run_jetson_p7_resident_service_smoke.sh` 与 `run_jetson_p8_resident_service_required.sh` 新增 `TEXT_DEVICE=\"${TEXT_DEVICE:-none}\"`，并显式传入 `--text-device \"${TEXT_DEVICE}\"`；Project5 resident client 会把历史 `cpu` 写法归一化到 llama.cpp 可接受的 `none`。 |
| 预期效果 | 让 resident text 完全留在 CPU 侧，释放 Jetson CUDA backend 给 resident VLM。代价是 text 解释延迟会变高，但当前 `TEXT_MAX_CALLS=2`，系统目标是先形成稳定并发窗口，不是追求 text 吞吐。 |
| `v6` 新证据 | 用户已按最新口径完成板端自检：`llama_cpp_resident_client.py` 已包含 `cpu -> none` 映射，`run_jetson_p7_resident_service_smoke.sh` 默认 `TEXT_DEVICE=none`。随后执行 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v6`，stdout 已不再停在 `ServiceTextWorker(...)`，而是在 `ServiceVlmWorker(...).resident_client.start()` 阶段失败，报 `resident llama.cpp VLM server exited during startup: exit_code=-11`。 |
| `v6` 直接证据 | text runtime log 显示 text server 已正常 `model loaded` 并监听 `http://127.0.0.1:50999`，且走的是 host-memory fit 路径；VLM runtime log 则显示 `CUDA0 : Xavier (6833 MiB, 2913 MiB free)`，随后再次出现 `NvMapMemAllocInternalTagged error 12`、`allocating 71.51 MiB on device 0: cudaMalloc failed: out of memory`、`failed to allocate compute pp buffers`。 |
| `v6` 当前可确定结论 | 到 `v6` 为止，可以确定 `TEXT_DEVICE=none` 已经修复了 text resident 的 CLI 参数问题；当前失败也不是新的随机 segfault，而是再次落回 VLM startup OOM。但与 `v4` 不同的是，这次 text 已经起在 CPU-only 路径上，因此当前更应怀疑的是“detector 先启动 + resident VLM startup”的容量冲突，而不是 text 仍在抢 GPU。 |
| 当前推断 | 现有 Jetson P7/P8 wrapper 仍沿用 `detector_start_order=early`，也就是 detector 会先初始化 TensorRT，再去起 text/VLM worker。`v6` 的 VLM log 只有 `2913 MiB free`，明显低于 standalone VLM 成功时的空闲量，因此下一步应先把 Jetson P7/P8 改成 `--detector-start-order after_workers`，把 detector 提前占用 GPU 的因素从实验里剥离出来。 |
| 下一步证据要求 | 使用更新后的 Jetson wrapper 复跑：`DETECTOR_START_ORDER=after_workers bash projects/05_alarm_system/scripts/service/run_jetson_p7_resident_service_smoke.sh`。如果这时 VLM 能起但 detector 后续失败，说明当前 Jetson 单板真实冲突已经从 `text+VLM` 收敛为 `detector+VLM`；如果 VLM 仍在 detector 未启动前就失败，则说明单独 resident VLM 之外的 service/runtime 差异仍需继续压缩。 |
| 回归要求 | 复跑 `P7` 时至少满足：1) text runtime log 不再出现 CLI 参数错误，并且最好不再显示 `CUDA0` 作为主设备；2) VLM server 能成功启动；3) `window_requirement_met=true`；4) `llm_call_count=2`、`vlm_call_count=2`；5) `drop_count=0`。 |
| 当前状态 | `text_device_none_applied_pending_after_workers_rerun` |

### P05-JETSON-LLAMA-DEVICE-NONE-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v5` |
| 模块 | llama.cpp / CLI 兼容性 |
| 现象 | 在 `P05-JETSON-RESIDENT-CONCURRENCY-CUDA-CAPACITY-001` 的第一次缓解尝试里，wrapper 将 text resident 设置为 `TEXT_DEVICE=cpu`。实际运行时，text server 在 startup 阶段直接退出，报 `resident llama.cpp server exited during startup: exit_code=1`。 |
| 直接证据 | `logs/runtime/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v5_llama_cpp_text_runtime/llama_cpp_resident_text_server.log` 第一行即报：`error while handling argument "--device": invalid device: cpu`，usage 说明里明确写的是 `--device <dev1,dev2,..>`，并标注 `none = don't offload`。 |
| 根因 | 当前 Jetson 上使用的这版 `llama-server` CLI 不接受 `cpu` 作为 `--device` 参数值。对它来说，真正表示“完全不 offload、只走 CPU”的值是 `none`。因此前一轮“把 text resident 固定到 CPU”的思路是对的，但传参字面值错了。 |
| 处理过程 | 第一步读取 `v5` 的 text runtime log，确认错误不是新的内存问题，而是启动参数被直接拒绝；第二步对照 `llama_cpp_resident_client.py` 现有命令拼装逻辑，确认 `args.text_device` 被原样透传；第三步在 Project5 client 中加入兼容层，把用户侧的 `cpu` 语义自动映射为 llama.cpp 可接受的 `none`；第四步同步把 Jetson `P7/P8` wrapper 默认值从 `TEXT_DEVICE=cpu` 改成 `TEXT_DEVICE=none`。 |
| 已落地修复 | `projects/05_alarm_system/scripts/service/llama_cpp_resident_client.py` 与 `llama_cpp_resident_vlm_client.py` 现在会把 `device=cpu` 归一化成 `--device none`；`run_jetson_p7_resident_service_smoke.sh`、`run_jetson_p8_resident_service_required.sh` 的默认 `TEXT_DEVICE` 也已改成 `none`。 |
| 操作注意 | 如果板端只同步了 shell wrapper、没有同步 `llama_cpp_resident_client.py` / `llama_cpp_resident_vlm_client.py`，或者仍然手工 `export TEXT_DEVICE=cpu` 后运行旧代码，就会再次复现同类失败。正式复测时应优先 `unset TEXT_DEVICE` 或显式 `export TEXT_DEVICE=none`。 |
| 回归要求 | 下一轮 `P7` 允许你继续沿用 `export TEXT_DEVICE=cpu`，因为 Project5 client 已兼容该别名；更推荐直接不设置或显式 `export TEXT_DEVICE=none`。通过标准仍然是：text server 成功启动、VLM server 成功启动、`window_requirement_met=true`、`drop_count=0`。 |
| 当前状态 | `fixed_by_cpu_alias_to_none` |

### P05-JETSON-RESIDENT-RUNTIME-BACKPRESSURE-001

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-13 |
| board | Jetson 8GB |
| 关联 run_id | `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v7`; `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` |
| 模块 | resident runtime / queue / timeout |
| 现象 | `after_workers` 后，Jetson P7 已经不再死于 worker startup。`v7` 首次拿到有效 10 分钟窗口，但最终 `drop_count=99`、`alarm_count=37/136`，说明 queue 被前两次真实请求拖死；`v8` 在更大的 `SERVICE_QUEUE_CAPACITY` 和更小 request budget 下，已经把这层问题收口为 `drop_count=0`、`alarm_count=136/136`。 |
| 直接证据 1 | `v7` stability raw：`benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v7_alarm_system_stability.jsonl`，其中 `window_requirement_met=true`、`detection_fps=28.813327`、`event_queue_depth=24`、`drop_count=99`。 |
| 直接证据 2 | `v8` stability raw：`benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8_alarm_system_stability.jsonl`，其中 `window_requirement_met=true`、`detection_fps=28.632848`、`event_queue_depth=91`、`drop_count=0`、`memory_mb=4866.0`、`swap_used_mb=2304.0`、`temperature_c=60.5`。 |
| 直接证据 3 | `v8` text raw：两次真实 text 调用都已 `pass`，同一 `resident_server_pid=60424`、`resident_model_load_count=1`，请求序号 `1/2`。 |
| 直接证据 4 | `v8` VLM raw：两次真实 VLM 调用分别记为 `RemoteDisconnected` 和 `timeout`，后续事件仅因 call budget 耗尽才退化为 fallback。 |
| 直接证据 5 | `v8` service log：`service_stop frames=18048 events=136 alarms=136 queue_dropped=0 asset_events=2 asset_success=2`，说明当前问题已经不再是 queue backpressure，而是 resident VLM request path。 |
| 根因判断 | `v7 -> v8` 已证明 queue 容量和 request 预算缓解是有效的。当前失败层级已从“真实 text/VLM 请求太慢导致队列打满”继续收口为“resident VLM request 本身不能稳定完成”，因此本条问题现在主要承担“v7 的 backpressure 已被缓解验证”的结案作用。 |
| 当前处理 | 继续保留 `SERVICE_QUEUE_CAPACITY=192`、`TEXT_MAX_TOKENS=64`、`TEXT_TIMEOUT_MS=180000`、`QWEN_NO_THINK=1`、`VLM_MAX_TOKENS=64`、`VLM_TIMEOUT_MS=210000` 作为 Jetson P7/P8 的默认收口参数；下一步不再优先调 queue，而是优先收口 VLM request path。 |
| 回归要求 | 下一轮 `P7/P8` 至少满足：1) `llm_pass_rows=2`；2) `vlm_pass_rows=2`；3) `drop_count=0` 持续保持；4) service log 不再出现 resident VLM request failed；5) `alarm_count=event_count`。 |
| 当前状态 | `queue_mitigation_verified_vlm_request_path_still_fails` |

## 必查风险

| 风险 | 检查状态 | 证据 | 结论 |
|---|---|---|---|
| 项目四准入证据缺失 | `checked` | `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` | Jetson text/image 有 B 级低频准入；video 为 D，不接入 |
| RK3588 项目四准入证据 | `checked` | `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` | RK3588 text/image 有 B 级低频准入；video 为 D，不接入 |
| VLM/LLM 阻塞检测 | `checked_post_detector_required30min` | `projects/05_alarm_system/reports/alarm_system_benchmark.md` | Jetson 30min detector pass，Project5 后处理链路 pass；仍不能写成完整并发常驻服务 |
| 告警 JSON 与检测事实冲突 | `schema_checked_required30min` | `benchmark/raw/05_alarm_system/jetson_8gb/alarms/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_alarms.jsonl` | Alarm JSON rows=397 schema pass；事实一致性抽检由 LLM bad rows=0 支撑 |
| 摄像头断流恢复失败 | `pending_project5_run` | `logs/failures/05_alarm_system/jetson_8gb/` | 必须异常注入 |
| 内存或 swap 过高 | `checked_required30min` | `logs/monitor/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_e2e_tegrastats.log` | memory `3001.0 MB`, swap `195.0 MB` |
| 温控降频 | `checked_required30min` | `projects/05_alarm_system/reports/stability_report.md` | temp peak `68.5 C`; power_w unavailable |

## RK3588 Astra S Camera Smoke 记录

| 字段 | 内容 |
|---|---|
| issue_id | P05-RK3588-ASTRA-CAMERA-SMOKE-001 |
| run_id | `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` |
| Project3 detector | Astra S OpenNI `2bc5/0402`, 17762 frames, 600.0 sec, FPS `29.6033`, p95 `121.51645 ms`, schema/trace pass |
| Project5 chain | detector adapter 17762 rows, event package 2 rows, real RKLLM rows 2 bad 0 contaminated 0, VLM route stub rows 2, Alarm JSON rows 2 |
| schema | event package pass, alarm JSON pass, per-event benchmark pass |
| decision | `camera_alarm_chain_smoke_pass_with_vlm_stub` |
| caveats | VLM route stub only；video disabled by project4；无 Project5 time-window stability raw；不声明真实 Qwen3-VL 或稳定性通过 |

## Jetson Required 30min 结案记录

| 字段 | 内容 |
|---|---|
| issue_id | P05-JETSON-REQUIRED30MIN-PASS-001 |
| run_id | `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` |
| Project3 detector | 54130 frames, 1800.0 sec, FPS `30.0722`, p95 `61.793955 ms`, schema/trace/aggregate pass |
| Project5 chain | detector adapter 54130 rows, event package 397 rows, LLM rows 10 bad 0, VLM route stub rows 3, Alarm JSON 397 rows |
| schema | event package pass, alarm JSON pass, per-event benchmark pass, stability pass |
| monitor | `memory_mb=3001.0`, `swap_used_mb=195.0`, `temperature_c=68.5`, `power_w=null` |
| decision | `pass_with_caveats` |
| caveats | VLM route stub only; video disabled by project4; tegrastats 无 power 字段；链路为 detector 后处理顺序验证，不声明完整并发常驻服务 |
## 2026-07-13 Source Mitigations

以下变更已经进入 Project5 当前源码，用于收口 Jetson 与清理 RK3588 产物：

| category | change | target issue / goal |
|---|---|---|
| Jetson detector | `ResidentProcessDetectorService` 新增冷启动重试，`run_alarm_service.py` 暴露 `--detector-start-retries`、`--detector-restart-delay-sec` | `P05-JETSON-RESIDENT-DETECTOR-CUDA-INIT-001` |
| Jetson VLM | `vlm_worker.py` 新增 `--vlm-request-retries`，`llama_cpp_multimodal_resident` 请求失败后允许重启 server 再试一次 | `P05-JETSON-RESIDENT-VLM-CUDA-OOM-001` / `P05-JETSON-RESIDENT-VLM-REQUEST-001` 在“startup 成功 / request timeout”阶段的收口 |
| Jetson VLM wrapper | `run_jetson_p6_resident_vlm_smoke.sh` 默认切到更保守的 CPU-first 配置：`VLM_CTX=1536`、`VLM_MAX_TOKENS=96`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、`VLM_IMAGE_MIN/MAX_TOKENS=512`，并新增 `VLM_DEVICE` 显式透传能力 | 降低首个多模态请求 timeout 概率，并允许在 Jetson 上固定 llama.cpp multimodal 的 device 路径做对照实验 |
| Jetson concurrency wrapper | `run_jetson_p7_resident_service_smoke.sh` / `run_jetson_p8_resident_service_required.sh` 默认新增 `TEXT_DEVICE=none`；Project5 llama.cpp resident client 兼容 `cpu -> none`；同时新增 `VLM_DEVICE` 显式透传能力 | 收口 `P05-JETSON-RESIDENT-CONCURRENCY-CUDA-CAPACITY-001` 与 `P05-JETSON-LLAMA-DEVICE-NONE-001`，把 CUDA 容量优先让给 VLM，并把 multimodal device 选择从 `auto` 变成可控实验变量 |
| RK3588 resident wrappers | `run_alarm_service.py` 新增 `--detector-start-order after_workers` 与 `vlm_real_calls_only` 下的预算内提前抽资产；`P7/P8/P9` 默认 `FRAME_CACHE_CAPACITY=512`，并在 `EXIT` 路径执行 `frame_cache_cleanup` | 减少运行中和运行后残留的大量 `frame_*.jpg` |

这些改动不代表问题已经解决，只代表后续复测不再停留在旧的失败路径上。

### P05-JETSON-P6-TEXT-DEVICE-AUTO-001

| 项目 | 记录 |
|---|---|
| board | Jetson 8GB |
| 关联 run_id | `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v1` |
| 模块 | P6 resident text smoke / llama.cpp device selection |
| 现象 | 在仅运行 resident text 与 VLM stub 的事实约束 smoke 中，`llama-server` 在准备就绪前退出，Python 侧报 `exit_code=-11`。该异常发生在 `ServiceTextWorker` 初始化，尚未消费事件、尚未执行 LLM 请求，也尚未进入最终 Alarm JSON 的事实约束逻辑。 |
| 根因判断 | P6 wrapper 当时只透传 `TEXT_NGL=0` 和 `TEXT_NO_KV_OFFLOAD=1`，没有传入 `--text-device`。对 CUDA 构建的 llama.cpp，`-ngl 0` 不等价于禁用 CUDA backend；缺省 `auto` 仍可能选择 CUDA，因而会受 Jetson 当前 CUDA/NvMap 可用空间与碎片状态影响。仅有 traceback 时不能把 `-11` 精确标为 OOM，必须以该 run 的 `llama_cpp_resident_text_server.log` 为准。 |
| 已落地修复 | `run_jetson_p6_resident_text_smoke.sh` 现在默认 `TEXT_DEVICE=none`，打印实际值，并显式透传 `--text-device "${TEXT_DEVICE}"`。resident client 将历史 `TEXT_DEVICE=cpu` 兼容映射为 llama.cpp 接受的 `none`。 |
| 复测口径 | 使用新的 `RUN_ID`，显式 `export TEXT_DEVICE=none`，保留 `TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1` 后运行 P6。若仍失败，先读取 `logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_cpp_runtime/llama_cpp_resident_text_server.log`，再判断是 CUDA/NvMap OOM、命令行参数不兼容还是模型文件/运行时异常。 |
| 当前状态 | `fixed_wrapper_default_pending_board_rerun` |

### P05-JETSON-P6-QWEN-THINK-BUDGET-001

| 项目 | 记录 |
|---|---|
| board | Jetson 8GB |
| 关联 run_id | `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v2` |
| 模块 | P6 resident text / Qwen3 completion budget |
| 现象 | `TEXT_DEVICE=none` 后服务稳定启动：同一 `resident_server_pid=1892338`、`resident_model_load_count=1` 完成三次真实请求。但三条 LLM 记录均为 `status=failed`、`output_tokens=256`、`final_output_tokens=0`，请求耗时约 67--83 秒。 |
| 直接证据 | server log 显示三次请求均正常完成：prompt eval 约 8.9 tok/s、decode 约 5.0 tok/s、每次 `n_decoded=256`、`truncated=0`。这说明不是 server 崩溃、OOM、HTTP timeout 或事实约束拦截；模型把生成预算用于 reasoning，未在上限前输出可解析的最终四行。 |
| 根因 | `run_jetson_p6_resident_text_smoke.sh` 没有把现有 `--qwen-no-think` 能力透传给 `run_alarm_service.py`。仅靠中文提示禁止思考不足以关闭 Qwen3 chat template 的默认 thinking 行为。 |
| 已落地修复 | P6 wrapper 新增 `QWEN_NO_THINK=${QWEN_NO_THINK:-1}`，值为 `1` 时显式传入 `--qwen-no-think`；默认 `TEXT_MAX_TOKENS` 从不适合告警四行输出的 `768` 收敛到 `128`。实际命令行仍允许按需覆盖，但 P6 验证不应关闭 no-think。 |
| 复测标准 | 使用新 `RUN_ID`，`QWEN_NO_THINK=1`、`TEXT_MAX_TOKENS=128`、`TEXT_DEVICE=none`。需要看到 `llm_rows=3`、`llm_bad_rows=0`、单一 pid、`model_load_count=[1]` 与单调递增 request index；最终 Alarm JSON 的 `json_fact_conflict` 行可存在，表示发布侧已用确定性模板替换事实冲突原文，而非实验失败。 |
| 当前状态 | `fixed_wrapper_default_pending_board_rerun` |

### P05-JETSON-P6-TEXT-FACT-GUARD-002

| 项目 | 记录 |
|---|---|
| board | Jetson 8GB |
| 关联 run_id | `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` |
| 验证目标 | 验证 resident Qwen3 text 的原始结果不可信时，最终 Alarm JSON 是否仍只发布 detector 事实。 |
| 常驻与性能证据 | `resident_server_pid=1901315`，`resident_model_load_count=1`，请求序号 `1/2/3`；三次真实请求分别为 `39.918s`、`25.531s`、`32.115s`，decode 约 `5.12/5.30/5.22 tok/s`，均无 thinking 输出。 |
| 原始文本审计 | 三条 `llm_outputs.jsonl` 均为真实 `status=pass`，但 person/multi-object 行输出 `medium` 与规则期望的 `high` 不一致，vehicle 行包含“未识别车辆”这一未由 detection 事实支持的断言。原文保留于 `llm_raw_output`。 |
| 发布侧结果 | 三条 Alarm JSON 全部设置 `json_fact_conflict=true`、记录 `fact_conflict_detail`，并将 publishable `llm_explanation` 替换为 detector-fact 四行模板；`fallback_status.alarm_json=fact_conflict_detected`。三条 Alarm JSON schema 均通过。 |
| 结论 | 原始 LLM 语义不能被视为无约束可靠，但 Project5 的发布边界已可验证地受控；这满足“不得新增检测外事实”的系统规范。 |
| 当前状态 | `closed_by_v3_publishable_text_guard_pass` |
