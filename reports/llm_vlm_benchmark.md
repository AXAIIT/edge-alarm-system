# llm_vlm_benchmark

当前状态：`jetson_required30min_qwen3_text_pass_rk3588_rkllm_text_smoke_pass_astra_camera_rkllm_pass_rk3588_real_vlm_runtime_smoke_pass_project5_service_vlm_smoke_pass_project5_service_rkllm_text_smoke_pass_project5_service_combined_rkllm_vlm_smoke_pass`。

本报告记录项目五系统整合场景下 LLM/VLM 的调用指标。项目四记录独立模型能力；本报告只在项目五 run 完成后记录接入检测、事件队列和告警 JSON 后的并行资源、延迟、超时和 fallback。

## 项目四继承基线

| board | model | task | runtime | 项目四等级 | selected run | p50 total ms | p95 total ms | decode tok/s | memory MB | swap MB | temp C | quality | project5 use |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Jetson 8GB | Qwen3-1.7B GGUF Q4_K_M | text | llama.cpp CUDA | `B_low_frequency` | `20260626_jetson_8gb_qwen3_1_7b_q4_k_m_gguf_llamacpp_cuda_text_ctx512_formal_v1` | 6277.0 | 6370.1 | 29.345 | 2146 | 218 | 53.5 | pass | 异步事件触发文本解释 |
| Jetson 8GB | Qwen3-VL-2B-Instruct Q4_K_M + mmproj F16 | image/ROI | llama.cpp CUDA mtmd/mmproj offload | `B_low_frequency` | `20260628_jetson_8gb_qwen3_vl_2b_q4_k_m_gguf_llamacpp_cuda_image_multi_input_formal_v2_mmproj_offload` | 24120.0 | 33107.15 | 2.483 | 3777 | 214 | 64.5 | pass | ROI/关键帧低频异步 |
| Jetson 8GB | Gemma 4 E2B IT QAT Q4_0 GGUF | text historical | llama.cpp CUDA | `B_low_frequency` historical | `20260624_jetson_8gb_gemma4_e2b_qat_q4_0_gguf_llamacpp_cuda_text_ctx512_ngl10_formal_v2` | 20546.5 | 21274.9 | 5.110 | 2437 | 0 | 56.0 | pass | 历史对照，不作为 selected 主线 |
| Jetson 8GB | Gemma 4 + mmproj | image historical | resident llama.cpp CUDA | `C_offline` | `20260625_jetson_8gb_gemma4_mmproj_image_yolo_bus_resident_benchmark_v1` | 141218.84 | 144606.345 | not_separated | 3066 | 363 | 62.5 | pass | 离线对照，不进入在线主线 |
| Jetson 8GB | SmolVLM2-500M-Video-Instruct | multiframe video | transformers blocked / llama.cpp diagnostic | `D_not_used` | `none_for_multiframe_video` |  |  |  | diagnostic_only | diagnostic_only | diagnostic_only | task_failed_multiframe | 不接入项目五视频理解 |
| RK3588 8GB | Qwen3-1.7B RKLLM W8A8 | text | RKLLM Runtime 1.3.0 | `B_low_frequency` | `20260701_rk3588_8gb_qwen3_1_7b_rkllm_text_ctx2048_formal_v2 + quality_v1 + quality_v2` | 15168.15 | 26628.865 | 12.712 | not_recorded_here | not_recorded_here | not_recorded_here | composite_pass | 异步事件触发文本解释 |
| RK3588 8GB | Qwen3-VL-2B RKNN vision + RKLLM decoder | image/ROI | RKNN vision encoder + RKLLM decoder | `B_low_frequency` | `20260703_rk3588_8gb_qwen3_vl_2b_rknn_rkllm_image_cn_formal_v2_max512` | 21391.0 | 57199.9 | not_separated | not_recorded_here | not_recorded_here | not_recorded_here | pass_with_caveat | ROI/关键帧低频异步 |
| RK3588 8GB | SmolVLM2-500M-Video-Instruct | video | diagnostic/failed route | `D_not_used` | `none_for_project5_video` |  |  |  | diagnostic_only | diagnostic_only | diagnostic_only | not_admitted_for_video | 不接入项目五视频理解 |

## 项目五系统整合指标

| board | model | task | 项目四等级 | call mode | first token ms | tokens/s | total ms | memory MB | swap MB | timeout rate | fallback status | status | raw result |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Jetson 8GB | Qwen3-1.7B GGUF Q4_K_M | text alarm explanation | `B_low_frequency` | `async_event_triggered`, llama.cpp `script` capture, thinking mode | not separated | captured in raw when available | per-event `total_ms` in raw; required 30min check rows=10 pass | 3001.0 system monitor peak | 195.0 system monitor | 0/10 in checked LLM rows | none in checked LLM rows | `required30min_text_model_pass` | `benchmark/raw/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_llm_outputs.jsonl` |
| Jetson 8GB | Qwen3-VL-2B-Instruct Q4_K_M + mmproj F16 | image/ROI explanation | `B_low_frequency` | route stub only |  |  |  | 3001.0 system monitor peak | 195.0 system monitor | not model execution | `not_model_execution` | `route_stub_only_rows_3` | `benchmark/raw/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_vlm_outputs.jsonl` |
| RK3588 8GB | Qwen3-1.7B RKLLM W8A8 | text alarm explanation | `B_low_frequency` | `rkllm`, Project4 single-turn runner wrapped by Project5 adapter | not separated in Project5 summary | first checked row `13.3427` | first checked row `14804.1 ms`; rows=3, bad=0, runtime-log contamination=0 | not captured as clean stability window in this smoke | not observed | 0/3 in checked RKLLM rows | none in checked RKLLM rows | `rkllm_text_smoke_pass` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1_llm_outputs.jsonl` |
| RK3588 8GB | Qwen3-1.7B RKLLM W8A8 | text alarm explanation | `B_low_frequency` | Project5 service `--text-mode rkllm`, cold-start single-shot worker | not separated | first checked row `11.3306` | first checked row `14583.9 ms`; rows=3, bad=0, contamination=0, `llm_call_count=3` | not captured as resident window | not observed | 0/3 checked rows | none in checked LLM rows; VLM intentionally stub | `project5_service_real_rkllm_single_shot_smoke_pass` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260709_rk3588_8gb_alarm_service_rkllm_worker_smoke_v2_llm_outputs.jsonl` |
| RK3588 8GB | Qwen3-1.7B RKLLM W8A8 | text alarm explanation | `B_low_frequency` | Project5 service combined RKLLM+VLM, cold-start single-shot worker | not separated | first checked row `12.6287` | first checked row `12836.8 ms`; rows=3, bad=0, contamination=0, `llm_call_count=3` | not captured as resident window | not observed | 0/3 checked rows | none in checked LLM rows; VLM also real in same service run | `project5_service_real_rkllm_vlm_single_shot_smoke_pass` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260709_rk3588_8gb_alarm_service_rkllm_vlm_worker_smoke_v1_llm_outputs.jsonl` |
| RK3588 8GB | Qwen3-1.7B RKLLM | text alarm explanation | `B_low_frequency` | template interface only |  |  |  | 1464.3 system monitor peak | not observed | not model execution | `template_alarm_json` | `required_template_rows_10` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_llm_outputs.jsonl` |
| RK3588 8GB | Qwen3-VL RKNN vision + RKLLM decoder | image/ROI explanation | `B_low_frequency` | route stub only |  |  |  | 1464.3 system monitor peak | not observed | not model execution | `not_model_execution` | `required_route_stub_rows_3` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_vlm_outputs.jsonl` |
| RK3588 8GB | Qwen3-VL RKNN vision + RKLLM decoder | image/ROI explanation | `B_low_frequency` | `rkllm_multimodal`, cold-start single-shot | not separated | mt384 rows=3: `9.9667`, `8.6903`, `9.1223` | mt384 rows=3: `20172`, `28550`, `17747` ms | not captured as clean window | not observed | 0/3 runtime timeout | none in runtime pass rows; previous row-2 truncation fixed by mt384 | `real_vlm_runtime_smoke_pass_mt384_quality_pass_single_shot` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1_vlm_outputs_mt384.jsonl` |
| RK3588 8GB | Qwen3-VL RKNN vision + RKLLM decoder | image/ROI explanation | `B_low_frequency` | Project5 service `--events-input` + `rkllm_multimodal`, cold-start single-shot worker | not separated | first row decode not separately summarized here | first row `21838 ms`; rows=3, bad=0, `vlm_call_count=3` | not captured as resident window | not observed | 0/3 checked rows | none in checked VLM rows; LLM intentionally template fallback | `project5_service_real_vlm_single_shot_smoke_pass` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260709_rk3588_8gb_alarm_service_vlm_worker_smoke_v1_vlm_outputs.jsonl` |
| RK3588 8GB | Qwen3-VL RKNN vision + RKLLM decoder | image/ROI explanation | `B_low_frequency` | Project5 service combined RKLLM+VLM, cold-start single-shot worker | not separated | first row decode not separately summarized here | first row `20644 ms`; rows=3, bad=0, `vlm_call_count=3` | not captured as resident window | not observed | 0/3 checked rows | none in checked VLM rows; RKLLM text also real in same service run | `project5_service_real_rkllm_vlm_single_shot_smoke_pass` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260709_rk3588_8gb_alarm_service_rkllm_vlm_worker_smoke_v1_vlm_outputs.jsonl` |

## Jetson Qwen3 Text Smoke Evidence

| run_id | model | backend | capture | max events | llm rows | bad rows | first status | first output | status |
|---|---|---|---|---:|---:|---:|---|---|---|
| `20260705_jetson_8gb_alarm_system_text_smoke_v1` | Qwen3-1.7B GGUF Q4_K_M | llama.cpp CUDA `llama-cli` | util-linux `script` session capture | 10 | 10 | 0 | `pass` | `1) 检测到疑似人员在指定区域内出现...` | `text_model_smoke_pass` |
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | Qwen3-1.7B GGUF Q4_K_M | llama.cpp CUDA `llama-cli` | util-linux `script` session capture | 10 | 10 | 0 | `pass` | `1) 置信度0.766，检测到1名行人...` | `required30min_text_pass` |

本次 smoke 证明真实 Qwen3-1.7B 可以在 Jetson 项目五事件输入上生成结构化中文告警解释，并且脚本能够从 llama.cpp 交互终端会话中提取 `[End thinking]` 后的最终四行。`thinking_included=True` 是 thinking 模式预期现象，不等于失败；正式写入 Alarm JSON 的字段是 `llm_explanation`。

注意：本地工作区曾存在同名旧失败 raw，内容为 `--no-conversation is not supported by llama-cli`。正式归档时必须以 Jetson 最新 `script` capture run 覆盖该 raw；如果 raw 中没有 `capture_mode=script` 和 `llm_raw_output`，不得引用为本次成功证据。

## Jetson 必填 Benchmark 指标

| category | required metric | source in raw/schema | current value |
|---|---|---|---|
| text latency | first token, prefill, decode tokens/s, total generation time | per-event raw: `llm_first_token_ms`, `llm_decode_tokens_per_s`, `llm_total_ms` | required 30min LLM raw rows=10; aggregate latency not separated in report; project4 p95 baseline `6370.1 ms` |
| text size | prompt tokens, output tokens, max output | model output raw/log | required 30min raw/log captured; max output `768` |
| image latency | image preprocess, first token, VLM total time | per-event raw: `vlm_total_ms`; model log | VLM route stub only rows=3; real Qwen3-VL project5 execution not claimed |
| input detail | ROI path, ROI size, keyframe path, image tokens | event package + VLM raw | event/alarm package rows=397 schema pass; VLM input remains route stub |
| quality | required answer pass, no fact overwrite, manual/automatic check | alarm JSON + quality table | LLM checked rows=10, bad rows=0; alarm JSON rows=397 schema pass |
| timeout | timeout count/rate, timeout threshold | per-event fallback + processed aggregate | LLM checked timeout/bad rows=0/10; VLM not model execution |
| resource | memory peak, swap, temp, CPU/GPU util, power | per-event raw + monitor log | system monitor memory `3001.0 MB`, swap `195.0 MB`, temp `68.5 C`; power unavailable in tegrastats |
| isolation | detector FPS/p95 delta while LLM/VLM enabled | detector benchmark + time-window raw | Project3 detector 30min pass: FPS `30.0722`, p95 `61.793955 ms`; Project5 post-detector chain pass, not fully concurrent service |

## Jetson Required 30min LLM/VLM Evidence

| run_id | detector frames | events | LLM rows | LLM bad rows | capture mode | VLM rows | alarm rows | system status |
|---|---:|---:|---:|---:|---|---:|---:|---|
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | 54130 | 397 | 10 | 0 | `script` | 3, route stub | 397 | `pass_with_vlm_stub_and_video_disabled` |

结论：Jetson required 30min 已证明真实 Qwen3-1.7B 文本解释可以低频接入项目五告警链路；Qwen3-VL 在项目五本轮仍只是路由 stub，不能写成真实 ROI/VLM 模型性能。视频理解按项目四结论禁用。

## RK3588 必填 Benchmark 指标

| category | required metric | source in raw/schema | inherited baseline |
|---|---|---|---|
| text latency | first token, decode tokens/s, total generation time | per-event raw + LLM raw/log | project4 p50 `15168.15 ms`, p95 `26628.865 ms`, decode `12.712 tok/s` |
| image latency | image preprocess, VLM total time, timeout rate | per-event raw + VLM raw/log | project4 p50 `21391.0 ms`, p95 `57199.9 ms` |
| input detail | ROI path, ROI size, keyframe path, image tokens | event package + VLM raw | event package rows=200 schema pass; VLM remains route stub |
| quality | no fact overwrite, pass_with_caveat 复核记录 | alarm JSON + quality table | RKLLM text smoke rows=3, bad=0, contamination=0; Alarm JSON rows=200 schema pass; no real RKNN-VLM quality claim |
| resource | memory peak, swap, temp, NPU/CPU util, power mode | per-event raw + monitor log | Project5 monitor rows=238; memory `1464.3 MB`, temp `38.85 C`; swap/power not observed |
| isolation | detector FPS/p95 delta while RKLLM/RKNN VLM enabled | detector benchmark + time-window raw | Project3 detector 1800s pass and Project5 interface chain pass; not real RKLLM/VLM concurrency |

## RK3588 Interface Smoke LLM/VLM Evidence

| run_id | detector frames | events | LLM rows | LLM backend | VLM rows | alarm rows | schemas | system status |
|---|---:|---:|---:|---|---:|---:|---|---|
| `20260708_rk3588_8gb_alarm_system_smoke_v1` | 18048 | 75 | 10 | template only | 3 route stub | 75 | event/alarm/per-event/stability pass | `interface_smoke_schema_pass` |
| `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | 54130 | 200 | 10 | template only | 3 route stub | 200 | event/alarm/per-event/stability pass | `required_interface_schema_pass_not_real_rkllm` |
| `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | reused from required run | 200 | 3 | real RKLLM W8A8 | 3 route stub | 200 | event/alarm/per-event pass | `rkllm_text_smoke_pass` |

结论：RK3588 required run 证明了 30 分钟 detector 后处理链路和结构化 schema 闭环；新增 `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` 证明 Project5 适配器能够调用真实 Qwen3-1.7B RKLLM 并生成干净中文告警解释。该 RKLLM run 是低频文本 smoke，不是 30 分钟真实模型并发稳定性；Qwen3-VL RKNN/RKLLM 在项目五仍为 route stub，不能写入真实 VLM p95 或真实 VLM 质量通过。

## RK3588 Real VLM Readiness

| requirement | current status | implementation |
|---|---|---|
| event package has `keyframe_path` or `roi_paths` | pass for 3 sampled events | `events_with_assets` rows=3, ROI counts `[1, 3, 1]`, schema pass |
| Project5 VLM can call real RK3588 multimodal runner | runtime pass | `run_vlm_roi_qa.py --mode rkllm_multimodal` wraps Project4 `run_rkllm_multimodal_once.sh` |
| Project5 resident VLM code path exists inside repo | board smoke pass on RK3588 | `src/vlm_client/rkllm_resident_vlm_server.cpp` + `scripts/service/rkllm_resident_vlm_client.py` + `scripts/build/build_rk3588_rkllm_vlm_runners.sh` + `run_alarm_service.py --vlm-mode rkllm_multimodal_resident`; validated by `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` |
| metrics/log capture | pass | per-event `metrics_json_path`, `runtime_log_path`, `vlm_total_ms`, `image_preprocess_ms`, `decode_tokens_per_s` written |
| pass condition | runtime pass with mt384 quality regression | `mode=rkllm_multimodal`, `status=pass`, `vlm_summary` non-empty, `image_path` exists; mt384 rows=3, bad=0, previous 128-token truncation fixed |

This smoke proves Project5 can feed real ROI assets into RK3588 Qwen3-VL RKNN/RKLLM and obtain VLM output. It is still a cold-start single-shot smoke, not detector/VLM concurrency stability, and not full quality acceptance. However, repo status is now stronger than single-shot only: `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` has already shown a Project5 local resident VLM server processing 3 events on the same pid with `resident_model_load_count=1`.

## RK3588 Real VLM Runtime Smoke Evidence

| run_id | event asset rows | ROI images | VLM backend | VLM rows | pass rows | total ms | decode tok/s | image preprocess ms | quality caveat | status |
|---|---:|---:|---|---:|---:|---|---|---|---|---|
| `20260708_rk3588_8gb_alarm_system_vlm_assets_smoke_v1` | 3 | 5 | Qwen3-VL RKNN vision 384 + RKLLM decoder W8A8 via Project4 `rkllm_multimodal_once` | 3 | 3 | mt384: `20172`, `28550`, `17747` | mt384: `9.9667`, `8.6903`, `9.1223` | mt384 metrics captured; image preprocess retained in per-event metrics | previous `multi_object_scene` truncation fixed by `--max-tokens 384` | `real_vlm_runtime_smoke_pass_mt384_quality_pass_single_shot` |
| `20260709_rk3588_8gb_alarm_service_vlm_worker_smoke_v1` | 3 | inherited from `events_with_assets` | Qwen3-VL RKNN vision 384 + RKLLM decoder W8A8 via Project5 service worker | 3 | 3 | first row `21838` | captured in VLM raw per event | service VLM metrics/log paths captured | proves Project5 service entry can call real VLM worker; still single-shot, not resident | `project5_service_real_vlm_single_shot_smoke_pass` |
| `20260709_rk3588_8gb_alarm_service_rkllm_vlm_worker_smoke_v1` | 3 | inherited from `events_with_assets` | Qwen3-VL RKNN vision 384 + RKLLM decoder W8A8 via Project5 service worker, combined with real RKLLM text | 3 | 3 | first row `20644` | captured in VLM raw per event | service VLM metrics/log paths captured | proves Project5 service entry can call real text+VLM workers in one run; still single-shot, not resident | `project5_service_real_rkllm_vlm_single_shot_smoke_pass` |
| `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1` | 3 | inherited from `events_with_assets` | Qwen3-VL RKNN vision 384 + RKLLM decoder W8A8 via Project5 local resident VLM server | 3 | 3 | service window `34.073 s` | resident request indexes `1/2/3` captured; per-event decode/runtime metrics retained | service VLM metrics/log/schema paths captured; same `resident_server_pid=2436647`, `resident_model_load_count=1`, `vlm_bad_rows=0` | proves Project5 local resident VLM worker can serve multiple events after one model load; still not detector+resident-VLM concurrency | `resident_vlm_worker_smoke_pass` |

## RK3588 RKLLM Text Smoke Evidence

| run_id | input events | model | backend | max events | LLM rows | bad rows | contaminated rows | first total ms | first decode tok/s | alarm rows | schemas | status |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `20260708_rk3588_8gb_alarm_system_rkllm_text_smoke_v1` | 200 | Qwen3-1.7B RKLLM W8A8 | RKLLM Runtime via Project4 `rkllm_single_turn` runner | 3 | 3 | 0 | 0 | 14804.1 | 13.3427 | 200 | event package pass; Alarm JSON pass; per-event raw pass | `rkllm_text_smoke_pass` |
| `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | 2 | Qwen3-1.7B RKLLM W8A8 | RKLLM Runtime via Project4 `rkllm_single_turn` runner | 2 | 2 | 0 | 0 | 13645.6 | 12.2845 | 2 | event package pass; Alarm JSON pass; per-event raw pass | `camera_rkllm_alarm_chain_smoke_pass` |
| `20260709_rk3588_8gb_alarm_service_rkllm_worker_smoke_v2` | 3 | Qwen3-1.7B RKLLM W8A8 | Project5 service text worker via Project5 local `rkllm_single_turn` adapter | 3 | 3 | 0 | 0 | 14583.9 | 11.3306 | 3 | event package pass; Alarm JSON pass; per-event raw pass; stability raw pass | `project5_service_real_rkllm_single_shot_smoke_pass` |
| `20260709_rk3588_8gb_alarm_service_rkllm_vlm_worker_smoke_v1` | 3 | Qwen3-1.7B RKLLM W8A8 | Project5 service text worker combined with real Qwen3-VL worker | 3 | 3 | 0 | 0 | 12836.8 | 12.6287 | 3 | event package pass; Alarm JSON pass; per-event raw pass; stability raw pass | `project5_service_real_rkllm_vlm_single_shot_smoke_pass` |

本次 smoke 复用了 `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` 的 detector/event 输入，目标是验证 Project5 对真实 RKLLM 文本解释的低频接入。`llm_explanation` 已经过 RKLLM runtime 日志清洗，检查结果为 `llm_contaminated_rows=0`。由于只执行 3 个解释样本且未生成独立 time-window stability raw，本 run 不替代 required 30min 稳定性结论。

`20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` 使用真实 Astra S OpenNI 摄像头事件输入，证明 camera source 下同一 RKLLM 文本解释路径可工作：2 条 `person_presence` 事件均生成 RKLLM 解释并进入 Alarm JSON。该 run 的 VLM 仍为 route stub，不能写成真实 Qwen3-VL 项目五摄像头能力。

## 质量检查

| event_id | model | expected | actual | pass/fail | issue_id |
|---|---|---|---|---|---|
| pending | Qwen3-1.7B | 不改写检测事实，输出可映射到 alarm JSON |  |  |  |
| pending | Qwen3-VL-2B | 只解释 ROI/关键帧，不替代 detector detections |  |  |  |

## Local Dry-run

| run_id | model route | rows | output | status |
|---|---|---:|---|---|
| `20260704_jetson_8gb_alarm_system_v3_task_domain_local_check` | Qwen3-1.7B template interface | 10 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_llm_outputs.jsonl` | `stub_template_fallback` |
| `20260704_jetson_8gb_alarm_system_v3_task_domain_local_check` | Qwen3-VL ROI interface stub | 3 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v3_task_domain_local_check_vlm_outputs.jsonl` | `not_model_execution` |
| `20260704_jetson_8gb_alarm_system_v2_rules_local_check` | Qwen3-1.7B template interface | 10 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v2_rules_local_check_llm_outputs.jsonl` | `stub_template_fallback` |
| `20260704_jetson_8gb_alarm_system_v2_rules_local_check` | Qwen3-VL ROI interface stub | 3 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_v2_rules_local_check_vlm_outputs.jsonl` | `not_model_execution` |
| `20260704_jetson_8gb_alarm_system_smoke_v1` | Qwen3-1.7B template interface | 542 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_llm_outputs.jsonl` | `stub_template_fallback` |
| `20260704_jetson_8gb_alarm_system_smoke_v1` | Qwen3-VL ROI interface stub | 20 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_vlm_outputs.jsonl` | `not_model_execution` |
| `20260704_jetson_8gb_alarm_system_local_dryrun` | Qwen3-1.7B template interface | 5 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_local_dryrun_llm_outputs.jsonl` | `stub_template_fallback` |
| `20260704_jetson_8gb_alarm_system_local_dryrun` | Qwen3-VL ROI interface stub | 5 | `benchmark/raw/05_alarm_system/jetson_8gb/20260704_jetson_8gb_alarm_system_local_dryrun_vlm_outputs.jsonl` | `not_model_execution` |

本地 dry-run 只验证路由和 fallback 字段，不计入 LLM/VLM 性能。

Jetson smoke v1 已验证 LLM/VLM 路由文件可被 alarm JSON builder 消费：542 个事件均有 template LLM 输出，前 20 个事件有 VLM stub 路由记录。该结果仍不代表真实 Qwen3-1.7B 或 Qwen3-VL 性能。

## MLPerf-style Summary: Jetson LLM/VLM Baseline

| field | value |
|---|---|
| Task | LLM/VLM alarm explanation under system integration |
| Board | Jetson 8GB |
| Text LLM | Qwen3-1.7B GGUF Q4_K_M, `B_low_frequency` |
| Image VLM | Qwen3-VL-2B-Instruct Q4_K_M + mmproj F16, `B_low_frequency` |
| Video model | disabled; SmolVLM2 multiframe video is `D_not_used` |
| Backend/runtime | llama.cpp CUDA; Qwen3-VL uses mtmd/mmproj offload |
| Dataset/input set | project4 fixed inputs for inherited baseline; project5 event ROI pending |
| Scenario | event-triggered async calls after detector and event queue integration |
| Quality target | JSON schema pass, no fact conflict, required fields complete |
| Performance result | inherited only: text p95 `6370.1 ms`; image p95 `33107.15 ms` |
| Resource result | inherited only: text peak `2146 MB`/swap `218 MB`; image peak `3777 MB`/swap `214 MB` |
| Stability result | Jetson required 30min pass, `window_sec=3223.0`, events=397, drop=0 |
| Raw result | `benchmark/raw/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_alarm_system_benchmark.jsonl` |
| Event package | rows=397, schema pass |
| Alarm JSON | rows=397, schema pass |
| Known limitations | 不能把 `B_low_frequency` 写成强实时在线能力；本轮 VLM 为 route stub，video disabled，power_w unavailable，链路为 detector 后处理顺序执行而非完整并发服务 |
