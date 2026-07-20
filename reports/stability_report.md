# stability_report

当前状态：`dual_board_target_pass_publishable_text_guard_pass`。

项目五稳定性必须覆盖高频检测、低频解释、事件队列、告警 JSON 和异常恢复。项目三稳定性只能作为检测链路基线，不能替代项目五系统稳定性。

## Jetson 继承检测稳定性

| run_id | tier | target sec | actual sec | FPS | p95 ms | p99 ms | memory peak MB | swap | temp max C | queue max | drop rate | restart/crash | status |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|---|
| `20260617_jetson_8gb_yolo11n_tensorrt_stability_smoke_playlist80_noout` | smoke | 600 | 596.0 | 30.1091 | 52.7732 | 55.0918 | 2317.0 | not_recorded | 57.5 | 7 | 0.00571 | 0/0 | `pass_noout_baseline` |
| `20260617_jetson_8gb_yolo11n_tensorrt_stability_short_playlist80_noout` | short_sustained | 1800 | 1797.0 | 30.0395 | 71.7296 | 74.4355 | 2226.0 | not_recorded | 60.5 | 8 | 0.00207 | 0/0 | `pass_noout_baseline` |
| `20260617_jetson_8gb_yolo11n_tensorrt_stability_acceptance_playlist80_noout` | acceptance_sustained | 7200 | 7196.0 | 30.0573 | 52.0953 | 53.9539 | 3920.0 | not_recorded | 60.0 | 7 | 0.00051 | 0/0 | `pass_noout_baseline` |

## 项目五稳定性计划

| board | duration | stability tier | input source | model combo | required calls | status | raw result | monitor log |
|---|---:|---|---|---|---|---|---|---|
| Jetson 8GB | 10 min | smoke | Project3 detector raw replay from `20260704_jetson_8gb_alarm_system_smoke_v1` | `jetson_8gb_alarm_combo_v2_project4_selected` | detector adapter + event + real Qwen3 text smoke; VLM route stub; video disabled | `schema_pass_raw_replay_not_verified` | `benchmark/raw/05_alarm_system/jetson_8gb/20260707_jetson_8gb_alarm_system_stability_smoke_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260707_jetson_8gb_alarm_system_stability_smoke_v1_tegrastats.log` |
| Jetson 8GB | 10 min | smoke | Project3 realtime detector 600s + Project5 post-detector explanation chain | `jetson_8gb_alarm_combo_v2_project4_selected` | detector realtime + event + real Qwen3 text smoke; VLM route stub; video disabled | `pass_with_caveat_user_accepted` | `benchmark/raw/03_video_pipeline/jetson_8gb/20260707_jetson_8gb_alarm_system_realtime10min_v1.jsonl`; `benchmark/raw/05_alarm_system/jetson_8gb/alarms/20260707_jetson_8gb_alarm_system_realtime10min_v1_alarms.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260707_jetson_8gb_alarm_system_realtime10min_v1_e2e_tegrastats.log` |
| Jetson 8GB | 10 min | smoke | Project5 local resident detector service + template/stub workers | `jetson_8gb_alarm_combo_v2_project4_selected` | Project5 local TensorRT detector `resident_process` + event + template LLM + VLM stub + online AlarmSink | `resident_detector_smoke_pass_with_template_stub_workers` | `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_tegrastats.log` |
| Jetson 8GB | not applicable | resident text worker smoke | Project5 `--events-input` + `llama_cpp_resident` + VLM stub | `jetson_8gb_alarm_combo_v2_project4_selected` | resident llama.cpp rows=3, same pid/load_count=1; detector skipped | `resident_text_worker_smoke_pass_not_detector_concurrency` | `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_text_smoke_v1_alarm_system_stability.jsonl` | no independent monitor; service log + llama server reuse evidence only |
| Jetson 8GB | not applicable | resident VLM worker smoke | Project5 `--events-input` + `llama_cpp_multimodal_resident` + asset replay | `jetson_8gb_alarm_combo_v2_project4_selected` | standalone multimodal `llama-server` pass; `vlm_rows=3`、`vlm_bad_rows=0`、same pid/load_count=1; detector skipped | `resident_vlm_worker_smoke_pass` | `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4_alarm_system_stability.jsonl` | no independent monitor; service log + multimodal runtime log prove reuse |
| Jetson 8GB | 10 min | smoke | Project5 local resident detector + resident text/VLM workers | `jetson_8gb_alarm_combo_v2_project4_selected` | P7 并发窗口已进入有效时间窗；detector 与 resident text 正常，真实 resident VLM 两次请求分别报 `RemoteDisconnected` 与 `timeout` | `valid_window_but_resident_vlm_request_failed` | `benchmark/raw/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8_tegrastats.log` |
| Jetson 8GB | 10 min | Route A smoke | Project5 local resident detector + resident VLM + template text | `jetson_8gb_alarm_combo_v2_project4_selected` | `window_requirement_met=true`、`detection_fps=26.685435`、`event_count=136`、`alarm_count=136`、`llm_call_count=0`、`vlm_call_count=2`、`drop_count=0`，但两次真实图片请求都 timeout | `route_a_valid_window_but_vlm_request_timeout` | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1_tegrastats.log` |
| Jetson 8GB | 10 min | Route B realtime smoke | Project5 local resident detector + resident text + VLM stub | `jetson_8gb_alarm_combo_v2_project4_selected` | `window_requirement_met=true`、`detection_fps=29.448237`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`，同一 text resident pid/load_count 复用；但 sampled text output 出现 `vehicle_presence/car -> 未佩戴安全帽` | `route_b_realtime_runtime_pass_with_text_fact_drift_caveat` | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1_tegrastats.log` |
| Jetson 8GB | not applicable | Route B async enrichment smoke | Project5 `--events-input` + resident VLM + asset replay | `jetson_8gb_alarm_combo_v2_project4_selected` | `event_count=3`、`alarm_count=3`、`llm_call_count=0`、`vlm_call_count=2`、`drop_count=0`，但两次真实图片请求继续 timeout | `route_b_async_vlm_timeout_reproduced` | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1_alarm_system_stability.jsonl` | no independent monitor; service log + multimodal runtime log show timeout reproduced |
| Jetson 8GB | 10 min | Route B dual-service smoke | Project5 realtime `resident detector + resident text + VLM stub` plus second async VLM worker process | `jetson_8gb_alarm_combo_v2_project4_selected` | realtime lane `window_requirement_met=true`、`detection_fps=28.741394`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`vlm_call_count=0`、`drop_count=0`、`restart_count=0`；async worker `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`，成功行不再依赖 retry1，但 fallback 行仍报 `RemoteDisconnected` | `route_b_dual_service_runtime_pass_async_vlm_partial_pass_v4` | `benchmark/raw/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4_tegrastats.log` |
| Jetson 8GB | 30 min | required | Project5 accepted Route-B：resident detector + resident text + postrun async VLM enrichment | `jetson_8gb_alarm_combo_v2_project4_selected` | realtime lane `1800s` + postrun async VLM `2/2 pass` | `resident_service_required_route_b_postrun_single_board` | `benchmark/raw/05_alarm_system/jetson_8gb/20260715_jetson_8gb_alarm_service_route_b_required_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260715_jetson_8gb_alarm_service_route_b_required_v1_tegrastats.log` |
| Jetson 8GB | 120 min | target | Project5 accepted Route-B：resident detector + resident text + postrun async VLM enrichment | `jetson_8gb_alarm_combo_v2_project4_selected` | realtime lane `7200s` + postrun async VLM `2/2 pass`；预热参数 `VLM_ONCE_PREWARM_REQUEST=1`、`VLM_ONCE_PREWARM_MAX_TOKENS=8` 已验证有效 | `resident_service_target_route_b_postrun_single_board` | `benchmark/raw/05_alarm_system/jetson_8gb/20260717_jetson_8gb_alarm_service_route_b_target_v3_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/jetson_8gb/20260717_jetson_8gb_alarm_service_route_b_target_v3_tegrastats.log` |
| RK3588 8GB | 10 min | smoke | Project3 realtime detector 600s + Project5 interface chain | `rk3588_8gb_alarm_combo_v1` | detector + event + template LLM + VLM route stub + video disabled | `schema_pass_not_stability_evidence` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_smoke_v1_alarm_system_stability.jsonl` | not captured |
| RK3588 8GB | 10 min | smoke | Project5 local resident detector service + template/stub workers | `rk3588_8gb_alarm_combo_v1` | Project5 local RKNN detector `resident_process` + event + template LLM + VLM stub + online AlarmSink | `resident_detector_smoke_pass_with_template_stub_workers` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/rk3588_8gb/20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2_rknpu_monitor.log` |
| RK3588 8GB | 10 min | smoke | Project5 local resident detector + frame-cache + resident text/VLM workers | `rk3588_8gb_alarm_combo_v1` | Project5 local RKNN detector `resident_process` + resident RKLLM + resident Qwen3-VL + online AlarmSink | `resident_service_smoke_pass_with_resident_text_vlm_workers` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3_rknpu_monitor.log` |
| RK3588 8GB | 30 min | required | Project5 local resident detector + frame-cache + resident text/VLM workers | `rk3588_8gb_alarm_combo_v1` | Project5 local RKNN detector `resident_process` + resident RKLLM + resident Qwen3-VL + online AlarmSink | `resident_service_required_pass_with_resident_text_vlm_workers` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_required_v2_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_required_v2_rknpu_monitor.log` |
| RK3588 8GB | 30 min | required | Project3 realtime detector 1800s + Project5 interface chain | `rk3588_8gb_alarm_combo_v1` | detector + event + template LLM + VLM route stub + video disabled | `required_interface_schema_pass_not_real_model` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_rknpu_monitor.log` |
| RK3588 8GB | not applicable | text smoke | Reused required event input + real RKLLM text explanation | `rk3588_8gb_alarm_combo_v1` | real RKLLM rows=3; VLM route stub + video disabled | `rkllm_text_smoke_pass_not_stability` | no independent stability raw | no clean stability monitor window |
| RK3588 8GB | not applicable | resident text worker smoke | Project5 `--events-input` + `rkllm_resident` + VLM stub | `rk3588_8gb_alarm_combo_v1` | resident RKLLM rows=3, same pid/load_count=1; VLM stub + video disabled | `resident_text_worker_smoke_pass_not_detector_concurrency` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1_alarm_system_stability.jsonl` | no independent monitor; service log + resident runtime log only |
| RK3588 8GB | not applicable | camera alarm-chain smoke | Astra S OpenNI camera detector + real RKLLM text explanation | `rk3588_8gb_alarm_combo_v1` | camera detector + event + real RKLLM rows=2; VLM route stub + video disabled | `camera_alarm_chain_smoke_pass_not_stability` | no independent stability raw | detector monitor only |
| RK3588 8GB | not applicable | real VLM ROI smoke | Project3 saved video + extracted ROI assets + real Qwen3-VL mt384 | `rk3588_8gb_alarm_combo_v1` | events_with_assets rows=3; real VLM rows=3; Alarm JSON/per-event schema pass | `real_vlm_runtime_smoke_mt384_alarm_json_per_event_schema_pass_single_shot` | no independent stability raw | no resident service monitor |
| RK3588 8GB | 120 min | target | Project5 local resident detector + frame-cache + resident text/VLM workers | `rk3588_8gb_alarm_combo_v1` | detector + event + resident text/VLM limited calls + video disabled | `resident_service_target_pass_with_resident_text_vlm_workers_single_board` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_target_v2_alarm_system_stability.jsonl` | `logs/monitor/05_alarm_system/rk3588_8gb/20260713_rk3588_8gb_alarm_service_resident_target_v2_rknpu_monitor.log` |

## 稳定性指标

| board | duration | events | alarms | detector FPS min | e2e p95 ms | memory growth MB/h | swap max MB | temp max C | fallback count | error count | pass/fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Jetson 8GB | 10 min raw replay smoke | 136 | 136 | not measured | not measured | not measured | 195.0 | 67.0 | 136 boundary fallbacks | 0 | `not_verified` |
| Jetson 8GB | 10 min realtime detector + post-detector explanation | 136 | 136 | 30.1302 | not measured | not measured | captured in overlong monitor | captured in overlong monitor | 136 boundary fallbacks | 0 | `pass_with_caveat` |
| Jetson 8GB | 10 min resident detector smoke | 136 | 136 | 29.458286 | not measured | not measured | 195.0 | 50.0 | 136 template/stub boundary fallbacks | 0 | `resident_detector_smoke_pass_with_template_stub_workers` |
| Jetson 8GB | resident text worker smoke | 3 | 3 | detector skipped; `--events-input` | not measured | not measured | not observed | not captured | 3 stub/video boundary fallbacks | 0 | `resident_text_worker_smoke_pass_not_stability` |
| Jetson 8GB | resident VLM worker smoke | 3 | 3 | detector skipped; `--events-input` | same pid/load_count=1 across 3 image requests | not measured | not observed | not captured | 3 template/video boundary fallbacks | 0 service-level schema errors | `resident_vlm_worker_smoke_pass` |
| Jetson 8GB | 10 min resident service smoke | 136 | 136 | 28.632848 | not measured | not measured | 2304.0 | 60.5 | 136 boundary/budget fallback rows | 0 | `valid_window_but_resident_vlm_request_failed` |
| Jetson 8GB | 30 min Route-B required | 397 | 397 | 29.76161 | not measured | not measured | 1139.0 | 55.5 | 397 boundary fallbacks in realtime lane; async VLM 2/2 pass | 0 | `resident_service_required_route_b_postrun_single_board` |
| Jetson 8GB | 120 min Route-B target | 1550 | 1550 | 29.989231 | not measured | not measured | 1139.0 | 56.0 | 1548 boundary fallbacks in realtime lane; async VLM 2/2 pass | 0 | `resident_service_target_route_b_postrun_single_board` |
| RK3588 8GB | 10 min interface smoke | 75 | 75 | 30.08 | not measured | not measured | not observed | not observed | 75 boundary fallbacks | 0 | `schema_pass_not_verified` |
| RK3588 8GB | 10 min resident detector smoke | 75 | 75 | 30.035697 | not measured | not measured | 477.5 | 58.23 | 75 template/stub boundary fallbacks | 0 | `resident_detector_smoke_pass_with_template_stub_workers` |
| RK3588 8GB | 10 min resident service smoke | 75 | 75 | 29.89495 | not measured | not measured | 483.5 | 58.23 | 73 budget/fallback boundary rows | 0 | `resident_service_smoke_pass_with_resident_text_vlm_workers` |
| RK3588 8GB | 30 min resident service required | 200 | 200 | 30.010783 | not measured | not measured | 484.0 | 62.85 | 198 budget/fallback boundary rows | 0 | `resident_service_required_pass_with_resident_text_vlm_workers` |
| RK3588 8GB | 120 min resident service target | 765 | 765 | 30.054365 | not measured | not measured | 484.2 | 62.85 | 763 budget/fallback boundary rows | 0 | `resident_service_target_pass_with_resident_text_vlm_workers_single_board` |
| RK3588 8GB | 30 min required interface | 200 | 200 | 30.0722 | not measured | not measured | not observed | 38.85 | 200 boundary fallbacks | 0 | `required_interface_schema_pass_not_real_model` |
| RK3588 8GB | RKLLM text smoke | 200 | 200 | reused required detector input | not measured | not measured | not observed | not captured | VLM/video boundary fallbacks | 0 in checked LLM rows | `rkllm_text_smoke_pass_not_stability` |
| RK3588 8GB | resident text worker smoke | 3 | 3 | detector skipped; `--events-input` | not measured | not measured | not observed | not captured | 3 stub/video boundary fallbacks | 0 | `resident_text_worker_smoke_pass_not_stability` |
| RK3588 8GB | real VLM mt384 smoke | 3 asset events | 3 | reused Project3 detector input | max 28550 ms | not measured | not observed | not captured | LLM template/video disabled boundary | 0 in checked VLM rows | `real_vlm_single_shot_not_stability` |

## Time-window Raw 字段完整性

| field group | required fields | current Jetson status |
|---|---|---|
| identity | run_id, timestamp, board, target, environment_baseline_id, model_combo_id, input_source_id | `schema_pass_text_smoke` |
| throughput | detection_fps, event_count, alarm_count, vlm_call_count, llm_call_count | required run captured: detector FPS 30.0722, events=397, alarms=397, LLM=10, VLM route=3 |
| alarm semantics | event_count_by_alarm_domain, event_count_by_alarm_type, fallback_count_by_alarm_domain | `schema_pass_text_smoke` |
| queue | event_queue_depth, drop_count | `schema_pass_text_smoke` |
| latency | end_to_end_alarm_ms | not separated in current Project5 raw; detector latency available in Project3 summary |
| resource | memory_mb, swap_used_mb, temperature_c, power_w | required run captured memory=3001.0 MB, swap=195.0 MB, temp=68.5 C; power unavailable |
| resilience | fallback_count, error_count, restart_count, reconnect_count, service_status | required run captured fallback=397 boundary fallbacks, error=0, restart=0, reconnect=0, running |
| evidence | runtime_log_path, monitor_log_path, failure_log_path, related_troubleshooting_id | runtime and monitor paths captured |

## 异常注入

| board | fault | expected fallback | observed | recovered | issue_id |
|---|---|---|---|---|---|
| Jetson 8GB | camera/video source disconnect | reconnect or degraded source state |  |  | pending |
| Jetson 8GB | VLM timeout | skip VLM; keep detector facts and text/template alarm |  |  | pending |
| Jetson 8GB | LLM timeout | template alarm JSON |  |  | pending |
| Jetson 8GB | memory/swap pressure | disable VLM first; keep detector running; template fallback if needed |  |  | pending |
| Jetson 8GB | invalid JSON/fact conflict | schema repair or fact-conflict flag; issue record |  |  | pending |
| RK3588 8GB | camera/video source disconnect | reconnect or degraded source state |  |  | pending |
| RK3588 8GB | VLM timeout | skip VLM; keep detector facts and text/template alarm |  |  | pending |
| RK3588 8GB | LLM timeout | template alarm JSON |  |  | pending |
| RK3588 8GB | invalid JSON/fact conflict | schema repair or fact-conflict flag; issue record |  |  | pending |

Jetson latest update（`2026-07-14`）：

- `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已把 standalone resident VLM 从失败证据推进到通过证据：`vlm_rows=3`、`vlm_bad_rows=0`、同一 `resident_server_pid=4611`、`resident_model_load_count=1`、请求序号 `1/2/3`。
- `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 已证明 Jetson P7 不再停留在 worker startup 或 detector 冷启动阶段，而是已经达到 `window_requirement_met=true`、`drop_count=0` 的有效 10 分钟窗口。
- Jetson 当前阻塞点已继续收口为 resident multimodal request path：这轮两次真实 VLM 请求分别报 `RemoteDisconnected` 和 `timeout`；对应 service log 同时显示 `queue_dropped=0`，说明 queue backpressure 已不再是第一主因。
- `20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1` 与 `20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1` 已完成 `VLM_DEVICE=none` 对照实验：standalone P6 从已通过的 `v4` 退化为 `vlm_bad_rows=3`，并发 P7 则变成两次真实请求都 timeout，且 `detection_fps` 下降到 `21.425603`。因此 `VLM_DEVICE=none` 只能保留为诊断开关，不能升级为 Jetson 默认主线配置。
- `20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4` 已把 B 方案口径从 `v3` 更新为最新板端结果：realtime lane `window_sec=627.353`、`detection_fps=28.741394`、`event_count=136`、`alarm_count=136`、`llm_call_count=2`、`drop_count=0`、`restart_count=0`；async worker `async_vlm_rows=2`、`async_vlm_pass_rows=1`、`async_vlm_fallback_rows=1`，且成功行 `resident_retry_count=0`、`vlm_total_ms=229011.465`，说明这次真实 pass 不再依赖 retry1，但 fallback 行仍为 `RemoteDisconnected`。
- 同一 `v4` 还暴露了新的产物质量问题：成功行 `vlm_summary` / `vlm_raw_output` 为乱码中文；因此 Jetson Route B 当前不仅没有达到 `2/2 pass`，而且就算单条 pass 也还不能直接作为最终业务输出验收。

Jetson 当前推荐实验顺序（`2026-07-14`）：

1. `detector resident + VLM resident + text template`
2. `detector resident + text resident + VLM stub`
3. 复用第 2 步的 `events.jsonl`，单独执行 resident VLM async enrichment

这三步的含义必须分清：

- 第 1 步是看 live detector 压力下，resident multimodal request path 能否独立成立。
- 第 2 步是把 Jetson 实时主链路先收敛到 detector + text。
- 第 3 步才是当前版本里正确的“低频异步 VLM enrichment”实现方式；它不是同一实时 service 内的后台补写，而是第二条 Project5 service run 消费持久化事件。

## 结论

Jetson accepted Route-B 已完整覆盖单板 `P7/P8/P9`，RK3588 也已完整覆盖同窗 resident detector、resident text/VLM 的单板 `P7/P8/P9`。`20260717_p05_dual_board_target_v1` 进一步形成双板 2 小时 target accepted 证据：Jetson `window_sec=7217.22`、`detection_fps=30.000887`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`；RK3588 `window_sec=7203.72`、`detection_fps=30.042395`、`event_count=765`、`alarm_count=765`、`llm_call_count=2`、`vlm_call_count=2`、`drop_count=0`。两板实际启动相差 `22.5s`，有效重叠 `7194.72s`，超过双板 target 要求的 `6900s`，组级状态为 `dual_board_target_ready`。`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` 再确认 Jetson text 发布侧守卫：同一 resident server 一次加载三次请求，原文冲突由确定性 fallback 替换，三条 Alarm JSON schema 均通过。因此 runtime 与 publishable-text 稳定性主线均已完成。

## Interface Smoke Note

| run_id | scope | event rows | alarm rows | monitor | status |
|---|---|---:|---:|---|---|
| `20260704_jetson_8gb_alarm_system_smoke_v1` | structure-only smoke from project3 detector raw; old generic rule | 542 | 542 | project5 monitor not captured | `not_stability_evidence` |
| `20260705_jetson_8gb_alarm_system_text_smoke_v1` | text model smoke from project3 detector raw; real Qwen3 text rows=10; VLM route stub | 136 | 136 | project5 monitor not captured | `stability_raw_schema_pass_not_stability_evidence` |
| `20260707_jetson_8gb_alarm_system_stability_smoke_v1` | raw replay stability smoke with tegrastats; real Qwen3 text rows=10; VLM route stub | 136 | 136 | 553 tegrastats rows | `schema_pass_raw_replay_not_verified` |
| `20260707_jetson_8gb_alarm_system_realtime10min_v1` | Project3 realtime detector 599s pass, then Project5 post-detector explanation chain to Alarm JSON | 136 | 136 | 50867 tegrastats rows; window overlong | `pass_with_caveat_user_accepted` |
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | Project3 realtime detector 1800s pass, then Project5 post-detector explanation chain; four Project5 schema checks pass | 397 | 397 | 3206 tegrastats rows; clean required window | `pass` |
| `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` | Project5 local TensorRT detector resident-process 612.629s pass, template/stub workers online, four Project5 schema checks pass | 136 | 136 | 612+ tegrastats window, clean resident-detector smoke | `resident_detector_smoke_pass_with_template_stub_workers` |
| `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` | Project5 resident llama.cpp text worker pass, same pid/load_count=1 across 3 requests, four Project5 schema checks pass | 3 | 3 | no independent monitor; service log + llama-server reuse evidence only | `resident_text_worker_smoke_pass` |
| `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` | Project5 resident multimodal llama.cpp worker pass, same pid/load_count=1 across 3 image requests, four Project5 schema checks pass | 3 | 3 | no independent monitor; service log + multimodal runtime log prove reuse | `resident_vlm_worker_smoke_pass` |
| `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` | Project5 local resident detector + resident text/VLM 630.325s valid window; four Project5 schema checks pass; detector/text stay alive, queue drop is 0, but both real VLM requests fail | 136 | 136 | 648 tegrastats rows; valid concurrent window with request-path failure evidence | `valid_window_but_resident_vlm_request_failed` |
| `20260708_rk3588_8gb_alarm_system_smoke_v1` | Project3 RKNN detector 600s pass, then Project5 interface chain; four Project5 schema checks pass | 75 | 75 | Project5 monitor not captured | `schema_pass_not_stability_evidence` |
| `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` | Project5 local RKNN detector resident-process 600s pass, template/stub workers online, four Project5 schema checks pass | 75 | 75 | 556 RKNPU monitor rows; clean 600.885s window | `resident_detector_smoke_pass_with_template_stub_workers` |
| `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1` | Project5 resident RKLLM text worker pass, same pid/load_count=1 across 3 requests, four Project5 schema checks pass | 3 | 3 | no monitor; service log + resident runtime log prove reuse | `resident_text_worker_smoke_pass` |
| `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` | Project5 local resident detector + frame-cache + resident text/VLM 603.714s pass; four Project5 schema checks pass | 75 | 75 | 561 RKNPU monitor rows; clean concurrent window | `resident_service_smoke_pass_with_resident_text_vlm_workers` |
| `20260713_rk3588_8gb_alarm_service_resident_required_v2` | Project5 local resident detector + frame-cache + resident text/VLM 1803.685s pass; four Project5 schema checks pass | 200 | 200 | 1665 RKNPU monitor rows; 30min clean window; text/VLM same pid/load_count=1 | `resident_service_required_pass_with_resident_text_vlm_workers` |
| `20260713_rk3588_8gb_alarm_service_resident_target_v2` | Project5 local resident detector + frame-cache + resident text/VLM 7204.045s pass; four Project5 schema checks pass | 765 | 765 | 6644 RKNPU monitor rows; 2h clean window; text/VLM same pid/load_count=1 | `resident_service_target_pass_with_resident_text_vlm_workers_single_board` |
| `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | Project3 RKNN detector 1800s pass, then Project5 interface chain; four Project5 schema checks pass | 200 | 200 | 238 RKNPU monitor rows | `required_interface_schema_pass_not_real_model` |
| `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | Reused required event input, real RKLLM text rows=3 bad=0 contaminated=0, Alarm JSON/per-event schema pass | 200 | 200 | no independent clean stability window | `rkllm_text_smoke_pass_not_stability` |
| `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | Astra S OpenNI camera detector 600s pass, real RKLLM text rows=2 bad=0 contaminated=0, Alarm JSON/per-event schema pass | 2 | 2 | Project3 detector RKNPU monitor only | `camera_alarm_chain_smoke_pass_not_stability` |

该 run 已生成 1 行 time-window stability raw，并通过 `benchmark/schemas/alarm_system_stability_schema.json` 校验；但没有项目五 monitor 采样，因此不能用于 10 分钟/30 分钟/2 小时稳定性通过结论。

`20260705_jetson_8gb_alarm_system_text_smoke_v1` 证明真实 Qwen3 文本解释和 Alarm JSON 结构链路可跑通，但仍没有 time-window raw、monitor 资源采样、异常注入和 30 分钟 required run。因此当前 Jetson 项目五状态只能写为 `not_verified_text_model_smoke`，不能写为稳定性通过。

## Text Smoke Stability Raw

| run_id | window_sec | event_count | alarm_count | alarm_type distribution | llm_call_count | vlm_call_count | queue_depth | fallback_count | schema | status |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|---|
| `20260705_jetson_8gb_alarm_system_text_smoke_v1` | 600.0 | 136 | 136 | person_presence=31, vehicle_presence=55, multi_object_scene=50 | 10 | 3 | 4 | 136 | pass | `not_verified` |
| `20260708_rk3588_8gb_alarm_system_smoke_v1` | 600.0 | 75 | 75 | person_presence=17, vehicle_presence=32, multi_object_scene=26 | 0 template model calls | 3 | 4 | 75 | pass | `not_verified` |
| `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` | 600.885 | 75 | 75 | person_presence=17, vehicle_presence=32, multi_object_scene=26 | 0 template model calls | 0 stub model calls | 3 | 75 | pass | `not_verified` |
| `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1` | 34.314 | 3 | 3 | person_presence=1, multi_object_scene=1, vehicle_presence=1 | 3 resident model calls | 0 stub model calls | 3 | 3 | pass | `not_verified` |
| `20260713_rk3588_8gb_alarm_service_resident_concurrency_smoke_v3` | 603.714 | 75 | 75 | person_presence=17, vehicle_presence=32, multi_object_scene=26 | 2 resident model calls | 2 resident model calls | 19 | 73 | pass | `not_verified` |
| `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` | 74.571 | 3 | 3 | person_presence=1, vehicle_presence=1, multi_object_scene=1 | 3 resident model calls | 0 stub model calls | 3 | 3 | pass | `not_verified` |
| `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` | 612.629 | 136 | 136 | person_presence=31, vehicle_presence=55, multi_object_scene=50 | 0 template model calls | 0 stub model calls | 3 | 136 | pass | `not_verified` |
| `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` | 630.325 | 136 | 136 | person_presence=31, vehicle_presence=55, multi_object_scene=50 | 2 resident model calls | 2 resident model calls | 91 | 136 | pass | `not_verified` |
| `20260713_rk3588_8gb_alarm_service_resident_required_v2` | 1803.685 | 200 | 200 | person_presence=47, vehicle_presence=86, multi_object_scene=67 | 2 resident model calls | 2 resident model calls | 24 | 198 | pass | `not_verified` |
| `20260713_rk3588_8gb_alarm_service_resident_target_v2` | 7204.045 | 765 | 765 | person_presence=171, vehicle_presence=333, multi_object_scene=261 | 2 resident model calls | 2 resident model calls | 23 | 763 | pass | `not_verified` |
| `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | 1800.0 | 200 | 200 | person_presence=47, vehicle_presence=86, multi_object_scene=67 | 0 template model calls | 3 | 6 | 200 | pass | `not_verified` |

`fallback_count=136` 不是 136 个运行错误，而是因为当前 Alarm JSON 每条都包含 VLM route stub 和 video disabled 降级状态。它说明视频/VLM 证据边界被记录下来；真实错误数为 `error_count=0`。

RK3588 `llm_call_count=0` 是因为本轮使用 template LLM interface，不计为真实 RKLLM 模型调用；`vlm_call_count=3` 也只是 route stub 记录。`fallback_count=75` 表示 VLM/video 边界降级被写入 Alarm JSON，不是运行错误。

`20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` 与 `20260708_rk3588_8gb_alarm_system_smoke_v1` 的区别是：前者由 Project5 本地 resident detector 进程在线生成 detector raw/event/alarm/per-event/stability，且 monitor 覆盖完整 600 秒窗口；后者只是复用 Project3 detector raw 的接口链路 smoke。

RK3588 required run 的 monitor rows 为 238，稳定性 raw 记录 `memory_mb=1464.3`、`temperature_c=38.85`，`swap_used_mb=null` 和 `power_w=null` 表示当前 RKNPU monitor 没有对应字段。该 run 错误、重启、重连均为 0，但真实 RKLLM/Qwen3-VL 未执行。

## Jetson Raw Replay Stability Smoke

| run_id | source detector raw | monitor rows | window_sec | events | alarms | llm calls | vlm calls | memory MB | swap MB | temp C | power W | queue depth | drop | errors | schema |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `20260707_jetson_8gb_alarm_system_stability_smoke_v1` | `benchmark/raw/03_video_pipeline/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_detector.jsonl` | 553 | 600.0 | 136 | 136 | 10 | 3 | 3368.0 | 195.0 | 67.0 | null | 4 | 0 | 0 | four schema checks pass |

该 run 是 Project3 detector raw replay 加 Project5 告警解释链路，不是摄像头/视频服务实时连续 10 分钟运行。因此它可作为资源采样和 schema 完整性 smoke，但不能替代 30 分钟 required stability，也不能用于声明 detector FPS 隔离通过。`power_w=null` 是因为本次 `tegrastats` 输出没有 `POM_5V_IN` 或 `VDD_IN` 功耗字段。

## Jetson Realtime 10min Smoke

| run_id | detector duration sec | detector FPS | detector schema | detector trace | detector raw rows | event rows | LLM rows | VLM rows | alarm rows | monitor rows | monitor window sec | user decision |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `20260707_jetson_8gb_alarm_system_realtime10min_v1` | 599.0 | 30.1302 | pass | pass | 18048 | 136 | 10, bad=0 | 3 route stub | 136 | 50867 | 51112 | `pass_with_caveat` |

判定说明：用户已裁定本轮通过。通过依据是 Project3 detector 10 分钟实时运行 schema/trace pass、`drop_frame_rate_total_estimated=0.0`、Project5 event/LLM/VLM route/Alarm JSON 链路完成且 LLM `bad=0`。证据边界是 E2E monitor 窗口过长，不能作为干净 600 秒资源窗口；Project5 per-event benchmark raw 和 stability raw 的最终 schema 本轮未继续生成。

## Jetson Required 30min

| run_id | detector duration sec | detector FPS | detector schema | detector trace | detector raw rows | events | alarms | LLM rows | VLM rows | monitor rows | window sec | memory MB | swap MB | temp C | schemas | status |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | 1800.0 | 30.0722 | pass | pass | 54130 | 397 | 397 | 10, bad=0 | 3 route stub | 3206 | 3223.0 | 3001.0 | 195.0 | 68.5 | four Project5 schema checks pass | `pass` |

判定说明：该 run 满足 Jetson 项目五 required 30min 的当前验收口径。Project3 detector 30 分钟实时运行通过，Project5 事件触发、真实 Qwen3 文本解释 smoke、VLM 路由记录、Alarm JSON、per-event raw、time-window stability raw 均完成并通过 schema。VLM 仍为 route stub，视频模型仍按项目四决策禁用；`fallback_count=397` 表示每条告警都记录了 VLM stub / video disabled 的证据边界，不是运行错误。
## 2026-07-13 Optimization Delta

### RK3588

| item | previous default | new default | reason |
|---|---:|---:|---|
| `FRAME_CACHE_CAPACITY` | 4096 | 512 | 4096 会留下过长的 detector frame ring；当前 `after_workers + vlm_real_calls_only + EXIT 清理` 已把真实 VLM 资产窗口压缩到更短区间，512 已足够覆盖前 N 个真实 VLM 事件 |
| frame-cache cleanup | success path only | `EXIT` path | 失败中断时也要删掉 `*_frame_cache/`，否则会残留大量 JPEG |

本轮 RK3588 优化不改变以下事实：

- `resident_service_smoke_pass_with_resident_text_vlm_workers`
- `resident_service_required_pass_with_resident_text_vlm_workers`
- `resident_service_target_pass_with_resident_text_vlm_workers_single_board`

也就是说，RK3588 当前是“在已通过主线的前提下优化运行卫生”，不是“重新争取通过”。

### Jetson

| item | new behavior | intended effect |
|---|---|---|
| detector start retry | `--detector-start-retries` + `--detector-restart-delay-sec` | 缓解 Jetson detector 在首轮 TensorRT/CUDA 初始化阶段的瞬时失败 |
| resident VLM request retry | `--vlm-request-retries` | 避免首个图片请求 timeout 后整条 resident VLM 立即失活 |
| once VLM request retry | `llama_cpp_multimodal_once` 现已真正消费 `--vlm-request-retries`；Jetson Route B dual-service 默认 `VLM_REQUEST_RETRIES=1` | 避免 async lane 首次 once 调用失败后立刻放弃，并把失败继续压缩到 request path 本身 |
| Jetson async-only timeout | `run_jetson_p7_route_b_dual_service_smoke.sh` 与 `run_jetson_p7_vlm_async_enrichment_smoke.sh` 默认把 `VLM_TIMEOUT_MS` / `VLM_STARTUP_TIMEOUT_MS` 提高到 `240000` | `v3` 的首次真实 pass 已耗时 `177413.336 ms`，继续使用 `180000 ms` 会让低频 enrichment 长期贴着上限运行 |
| P6 VLM defaults | timeout 提高到 180000ms，image tokens 降到 512，`VLM_REQUEST_RETRIES=1` | 先把 `resident_vlm_smoke` 从 timeout 推进到 pass |
| P7/P8 VLM defaults | `VLM_MAX_TOKENS` 降到 128，image tokens 降到 512 | 降低 Jetson 单板并发窗口中的首个 VLM 请求压力 |

### 后续实验口径

1. Jetson 先跑 `resident_vlm_smoke_v4`
2. Jetson 再跑 `resident_concurrency_smoke_v4`
3. RK3588 用新 frame-cache 参数复跑 `P7/P8/P9`
