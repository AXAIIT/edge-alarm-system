# Project 05 Service Runtime Boundary

This directory is reserved for the final Project 05 resident alarm service.

Final acceptance must not use Project 3 or Project 4 scripts as the resident runtime entrypoint. Project 3/4 artifacts, raw results, model files, and reports can be referenced as evidence or inputs, but Project 05 service orchestration must live under `projects/05_alarm_system`.

Local service entrypoints:

| File | Responsibility |
|---|---|
| `run_alarm_service.py` | Start the Project 05 service with resident detector process, detector replay, or event package input. |
| `run_rk3588_p3_resident_detector_smoke.sh` | RK3588 P3 child process; validates duration, schema, template/stub call counts, and always stops the monitor. It can be run directly in the foreground for debugging, or launched by the local control program. |
| `run_jetson_p4_resident_detector_smoke.sh` | Jetson P4 child process; runs the Project5 local TensorRT detector for one 10-minute window with template/stub workers, validates `requested_window_sec`, four schema families, and a non-empty `tegrastats` log. |
| `run_rk3588_p7_resident_service_smoke.sh` | RK3588 P7 child process; runs resident detector + frame-cache asset worker + resident text worker + resident VLM worker in one 10-minute window, validates monitor, schema, and same-pid/model-load reuse for both workers. |
| `run_rk3588_p8_resident_service_required.sh` | RK3588 P8 child process; extends the P7 topology to one 30-minute required window and additionally enforces `drop_count=0`, `requested_window_sec=1800`, and the same-pid/model-load reuse checks for both resident workers. |
| `run_rk3588_p9_resident_service_target.sh` | RK3588 P9 child process; extends the same topology to one 120-minute target window, sets `stability-tier=target`, and additionally enforces `drop_count=0`, `requested_window_sec=7200`, and the same-pid/model-load reuse checks for both resident workers. |
| `run_rk3588_camera_frame_cache_smoke.sh` | RK3588 camera/RTSP frame-cache smoke wrapper. It assembles the Project5 local detector command safely, clears stale outputs for a fresh `RUN_ID`, runs `resident_process` + `frame_cache_dir`, and validates the resulting stability/event artifacts. |
| `run_jetson_p6_resident_text_smoke.sh` | Jetson P6 text-worker smoke wrapper; reuses an existing Project5 event package, starts one Project5 local `llama-server`, and validates same-pid / `model_load_count=1` reuse across multiple text requests. Its defaults `TEXT_DEVICE=none` and `QWEN_NO_THINK=1` prevent implicit CUDA selection and stop Qwen3 reasoning text from consuming the four-line alarm output budget; `cpu` remains accepted as a client-side alias for `none`. |
| `run_jetson_p6_resident_vlm_smoke.sh` | Jetson P6 VLM-worker smoke wrapper; reuses an existing Project5 event package, lets the Project5 service backfill ROI/keyframe assets from the runtime playlist, starts one Project5 local multimodal `llama-server`, and validates same-pid / `model_load_count=1` reuse across multiple image requests. |
| `run_jetson_p7_detector_vlm_resident_smoke.sh` | Jetson route A wrapper; runs resident detector + resident VLM + template text in one 10-minute window. This isolates the multimodal request path under a live detector without also carrying resident text pressure. |
| `run_jetson_p7_detector_text_resident_smoke.sh` | Jetson route B realtime wrapper; runs resident detector + resident text with `vlm=stub` in one 10-minute window. This is the recommended realtime chain when VLM is moved out of band. |
| `run_async_vlm_enrichment.py` | Project5 local async VLM enrichment worker. It tails a persisted Project5 `events.jsonl`, optionally backfills ROI/keyframe assets, executes low-frequency real VLM calls, and rebuilds an enriched alarm snapshot keyed by `event_id`. |
| `run_jetson_p7_route_b_dual_service_smoke.sh` | Jetson route B integrated wrapper; starts the realtime `detector + resident text + vlm=stub` chain and a separate async VLM enrichment worker under the same `RUN_ID`. |
| `run_jetson_p9_route_b_postrun_target.sh` | Jetson P9 target wrapper; extends the accepted route-B postrun topology to one 120-minute target window and enforces `stability-tier=target`, `requested_window_sec=7200`, and `drop_count=0`. |
| `run_jetson_p7_vlm_async_enrichment_smoke.sh` | Jetson route B async-enrichment wrapper; now calls `run_async_vlm_enrichment.py` directly, treats the source `events.jsonl` as read-only input, backfills assets from `video_file` / `video_playlist` / `frame_cache_dir`, and writes `*_async_vlm_outputs.jsonl`, `*_alarm_enriched.jsonl`, and `*_alarm_enriched_benchmark.jsonl`. It no longer starts a second full `run_alarm_service.py` replay path for this diagnostic entrypoint. |
| `p05_rk3588_p3_control.py` | Project5 local P3 control. `run` blocks in the current terminal and mirrors errors immediately; `start` uses `start_new_session=True` so the P3 process survives an SSH disconnect. |
| `detector_service.py` | Start/tail a Project 05 local detector process, stream detector JSONL replay, or consume existing event packages into the bounded Project 05 event queue. |
| `event_queue.py` | Queue depth, cooldown, deduplication, drop policy, and metrics. |
| `asset_worker.py` | Project5 local keyframe/ROI asset worker for explicit `video_file` / `video_playlist` paths and detector-side `frame_cache_dir`. |
| `text_worker.py` | Template, single-shot, and resident RKLLM text worker adapter. |
| `run_demo/fact_guard.py` | Deterministic final-alarm text guard. It rejects unsupported objects, behaviors, confidence values, risk levels, or output shape, then replaces the publishable explanation with a detector-fact template while retaining the raw LLM output for audit. |
| `llama_cpp_resident_client.py` | Project5 local client for the resident `llama-server` HTTP protocol. |
| `llama_cpp_resident_vlm_client.py` | Project5 local client for the resident multimodal `llama-server` HTTP protocol. |
| `rkllm_resident_client.py` | Project5 local client for the resident RKLLM text server protocol. |
| `vlm_worker.py` | Stub, single-shot, and resident RKLLM multimodal VLM worker adapter. |
| `rkllm_resident_vlm_client.py` | Project5 local client for the resident RKLLM VLM server protocol. |
| `alarm_sink.py` | Write schema-safe Alarm JSON, per-event raw, and service logs. |

Worker modes currently supported by `run_alarm_service.py`:

| Option | Values | Current acceptance meaning |
|---|---|---|
| `--text-mode` | `template`, `llama_cpp`, `llama_cpp_resident`, `rkllm`, `rkllm_resident` | `llama_cpp` and `rkllm` are real single-shot calls; `llama_cpp_resident` starts one Project5 local `llama-server`; `rkllm_resident` starts one Project5 local persistent RKLLM text server. Both resident modes reuse one model load for multiple events. |
| `--vlm-mode` | `stub`, `rkllm_multimodal`, `rkllm_multimodal_resident`, `llama_cpp_multimodal_once`, `llama_cpp_multimodal_resident` | `rkllm_multimodal` is a real single-shot call; `rkllm_multimodal_resident` starts a Project5 local persistent vision+decoder server; `llama_cpp_multimodal_once` starts a temporary local multimodal `llama-server` for one request and then exits; `llama_cpp_multimodal_resident` starts one Project5 local multimodal `llama-server` with GGUF + mmproj and reuses one model load for multiple ROI/keyframe requests. |
| `--text-max-calls` | integer, `-1` means unlimited | Limits real text model calls; `0` forces template fallback. |
| LLM fact guard | always enabled at final Alarm JSON build | A real LLM output may be retained in raw JSONL, but any fact-conflicting result is not published: `json_fact_conflict=true`, `fact_conflict_detail` is populated, and `fallback_status.alarm_json=fact_conflict_detected`. |
| `--vlm-max-calls` | integer, `-1` means unlimited | Limits real VLM calls; `0` forces stub fallback. |
| `--asset-mode` | `none`, `source_media` | `source_media` enables Project5 local keyframe/ROI generation before VLM review. |
| `--asset-trigger-policy` | `all_events`, `vlm_real_calls_only` | `vlm_real_calls_only` only generates keyframe/ROI assets for events that will actually consume a real VLM call under the current service-level call budget. |
| `--detector-start-order` | `early`, `after_workers` | `early` starts the detector before resident text/VLM worker init; `after_workers` delays detector launch until workers are ready, which is useful when you want to shrink frame-cache retention on RK3588. |

Asset worker options:

| Option | Meaning | Current acceptance meaning |
|---|---|---|
| `--asset-source-type` | `video_file`, `video_playlist`, or `frame_cache_dir` | Explicit media type for Project5 local asset extraction. |
| `--asset-source-uri` | Real video file path, playlist path, or detector frame-cache directory | Must be a real local path; the service does not guess media sources. |
| `--asset-dir` | Output directory for keyframes and ROI images | Must stay under Project5-owned output paths in formal runs. |
| `--asset-playlist-loop` | Enable frame-id modulo playlist total frames | Required for looping runtime playlists such as `video_set_runtime_v1`. |

Current Jetson closure order:

1. `run_jetson_p4_resident_detector_smoke.sh`: prove resident detector + queue + AlarmSink.
2. `run_jetson_p6_resident_text_smoke.sh`: prove resident text reuse in isolation.
3. `run_jetson_p6_resident_vlm_smoke.sh`: prove resident VLM reuse in isolation.
4. `run_jetson_p7_detector_vlm_resident_smoke.sh`: live detector + resident VLM, with text held at template fallback.
5. `run_jetson_p7_detector_text_resident_smoke.sh`: live detector + resident text as the realtime chain, with `vlm=stub`.
6. `run_jetson_p7_route_b_dual_service_smoke.sh`: keep route-B realtime in one process and run the async VLM enrichment worker as a second Project5 process under the same `RUN_ID`.
7. `run_jetson_p8_route_b_postrun_required.sh`: accepted Jetson required topology. It reuses the route-B dual-service wrapper but forces `ASYNC_LAUNCH_MODE=postrun`, `stability-tier=required`, and `async_vlm_pass_rows >= 2`.
8. `run_jetson_p9_route_b_postrun_target.sh`: accepted Jetson target topology. It keeps the same route-B postrun shape and extends it to a 120-minute `target` window.
9. `run_jetson_p7_vlm_async_enrichment_smoke.sh`: fallback/manual route-B async-enrichment wrapper when you want to replay an existing event package without the integrated dual-service wrapper. This entrypoint now tails the existing event package directly and does not create a same-`RUN_ID` replacement `events.jsonl` or a synthetic stability raw.

Latest Jetson route results:

- `20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1` proves Route A can keep a valid 10-minute detector window, but both real resident VLM image requests still timeout.
- `20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1` proves the realtime `detector + resident text + vlm=stub` runtime chain, with one resident text pid and `model_load_count=1` reused across multiple requests.
- The same Route-B realtime run also exposed a semantic-quality issue: one real text output drifted from `vehicle_presence/car` into "no helmet". So the current accepted claim is runtime reuse, not explanation-quality acceptance.
- `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` proves the resident VLM timeout reproduces even in a second service run over persisted events. This means the current Jetson VLM blocker is the multimodal request path itself, not only same-window coexistence with resident text.
- `20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5` added a hard gate, `ASYNC_VLM_REQUIRE_PASS_ROWS=2`, and still failed at `1/2` real VLM pass. This confirmed that the remaining blocker in the `parallel` topology is not queue lifecycle but multimodal request-path interference inside the same runtime window.
- `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1` then switched the same route-B wrapper to `ASYNC_LAUNCH_MODE=postrun` and reached `async_vlm_rows=2`, `async_vlm_pass_rows=2`, `async_vlm_fallback_rows=0`, while the realtime lane still held `window_requirement_met=true`, `detection_fps=29.248229`, `event_count=136`, `alarm_count=136`, `drop_count=0`, and `llm_pass_rows=2`. This is the current accepted Jetson closure path: realtime `detector + resident text`, plus postrun async VLM enrichment under the same `RUN_ID`.
- `20260715_jetson_8gb_alarm_service_route_b_required_v1` then extended that same accepted topology to one 30-minute required window and reached `window_sec=1818.786`, `requested_window_sec=1800.0`, `window_requirement_met=true`, `stability_tier=required`, `detection_fps=29.76161`, `event_count=397`, `alarm_count=397`, `drop_count=0`, `llm_pass_rows=2`, `async_vlm_rows=2`, and `async_vlm_pass_rows=2`. This means Jetson single-board required evidence now exists on the accepted route.
- A dedicated Jetson target wrapper now also exists: `run_jetson_p9_route_b_postrun_target.sh`. It is the formal entrypoint for a future 2-hour Jetson target run on the same accepted topology.
- Dual-board orchestration is documented separately in `projects/05_alarm_system/specs/05N_双板联调执行流程.md`. There is still no single cross-board launcher; the accepted method is to run the Jetson and RK3588 formal wrappers in parallel under one `GROUP_RUN_ID`.

This order is deliberate. The current `run_alarm_service.py` implementation still consumes one event in a single alarm-worker thread and serializes `asset -> text -> vlm -> alarm`. So the integrated route-B implementation does not try to fake an in-process background lane. Instead, `run_jetson_p7_route_b_dual_service_smoke.sh` starts a second Project5 process, `run_async_vlm_enrichment.py`, which tails the persisted `events.jsonl` during the realtime run and writes a separate enriched alarm snapshot. The realtime detector/text lane therefore stays stable even when VLM is moved out of band.

Project5 local RK3588 text runner artifacts:

| File | Responsibility |
|---|---|
| `projects/05_alarm_system/src/llm_client/rkllm_single_turn.cpp` | Project5 local RKLLM single-turn text runner source. |
| `projects/05_alarm_system/src/llm_client/rkllm_resident_text_server.cpp` | Project5 local RKLLM resident text server source. |
| `projects/05_alarm_system/scripts/build/build_rk3588_rkllm_text_runners.sh` | Build and copy both RKLLM text runners into `projects/05_alarm_system/runners/`. |

Project5 local RK3588 VLM resident runner artifacts:

| File | Responsibility |
|---|---|
| `projects/05_alarm_system/src/vlm_client/rkllm_resident_vlm_server.cpp` | Project5 local RKLLM multimodal resident VLM server source. |
| `projects/05_alarm_system/src/vlm_client/image_enc.cc` | Project5 local RKNN vision encoder helper copied into Project5 boundary and redirected to stderr-safe logging. |
| `projects/05_alarm_system/scripts/build/build_rk3588_rkllm_vlm_runners.sh` | Build and copy the Project5 local resident VLM server into `projects/05_alarm_system/runners/`. |
| `projects/05_alarm_system/scripts/service/run_rk3588_vlm_resident_smoke.sh` | RK3588 resident VLM smoke wrapper; reuses an existing `events_with_assets` package and checks same pid / `model_load_count=1`. |

Current RK3588 resident text status:

- Code path is now local to Project5.
- Board-side runtime evidence is present in `20260710_rk3588_8gb_alarm_service_resident_text_smoke_v1`.
- The current accepted claim boundary is: same `resident_server_pid`, `model_load_count=1`, and multiple request reuse. It is not yet detector + resident-text concurrent required acceptance.

Asset worker status:

- Project5 local `asset_worker.py` is now implemented.
- It supports explicit `video_file` / `video_playlist` replay and detector-side `frame_cache_dir`.
- `frame_cache_dir` expects the Project5 local detector binary to write a bounded JPEG ring keyed by `frame_id`.
- When `--asset-trigger-policy vlm_real_calls_only` is used, the service now reserves the real VLM budget in queue order and eagerly extracts only those few required assets before enqueue. This prevents a slow first VLM request from forcing the detector-side frame cache to retain thousands of unrelated JPEGs.
- Direct live-camera retro-seek is still not supported; camera/RTSP exact-frame assets must come from detector-side frame cache rather than re-opening the source in Python.
- Board-side smoke evidence is still required before resident VLM acceptance.
- For RK3588 camera/OpenNI/RTSP smoke, prefer `run_rk3588_camera_frame_cache_smoke.sh` instead of hand-writing a long `--detector-command`. The wrapper exists specifically to avoid empty-token/quoting mistakes and to keep `frame_cache_dir`, logs, and output JSONL on the same fresh `RUN_ID`.

Current VLM boundary:

- `rkllm_multimodal` remains a single-shot route.
- `llama_cpp_multimodal_once` is now available for Jetson-oriented low-frequency async enrichment. It reuses the Project5 local multimodal HTTP path, but starts a temporary `llama-server` per event instead of trying to keep a long-lived resident VLM process alive.
- `rkllm_multimodal_resident` is now implemented under Project5 local source/build/runtime and has passed RK3588 board-side worker smoke in `20260711_rk3588_8gb_alarm_service_resident_vlm_smoke_v1`.
- The Project5 VLM prompt builder now injects an explicit `<image>` marker and the default runtime adapter has been corrected to Qwen3-VL token settings (`<|vision_start|>`, `<|vision_end|>`, `<|image_pad|>`, `template_style=qwen`). Older Project5 single-shot VLM service results should therefore be treated conservatively until rerun on the corrected path.

Current camera frame-cache smoke boundary:

- `run_rk3588_camera_frame_cache_smoke.sh` runs resident detector only.
- It deliberately uses `--text-mode template --text-max-calls 0` and `--vlm-mode stub --vlm-max-calls 0`.
- It also passes `--max-events ${MAX_EVENTS:-3}`, so the smoke can finish early once enough events are collected even if detector `--duration-sec` is larger.
- Therefore it proves detector + queue + frame-cache asset path only; it does not mean real LLM/VLM are resident in the same run.

Current JPG retention policy for resident-service wrappers:

- `run_rk3588_p7_resident_service_smoke.sh`, `run_rk3588_p8_resident_service_required.sh`, and `run_rk3588_p9_resident_service_target.sh` now set `--asset-trigger-policy vlm_real_calls_only`.
- These wrappers also pass `--detector-start-order after_workers`, so resident text/VLM are ready before the detector starts streaming frames.
- Combined with eager asset extraction, this means keyframe/ROI JPG files are only generated for the few events that really execute VLM, instead of every alarm event in the run, and the detector-side frame cache no longer needs to cover worker startup time.
- Both wrappers also default `CLEAN_FRAME_CACHE_ON_EXIT=1`, so the detector-side `frame_cache_dir` is treated as transient cache and removed after validation.
- `run_rk3588_camera_frame_cache_smoke.sh` also now defaults `CLEAN_FRAME_CACHE_ON_EXIT=1`; it keeps the small validated asset output, but deletes the large detector-side JPEG ring after the smoke finishes.

Current Jetson boundary:

- Project5 now has a dedicated Jetson P4 detector-resident wrapper.
- Jetson has a Project5-local `llama_cpp_resident` mode and a board-side P6 text-worker smoke pass in `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1`.
- Jetson now also has a Project5-local `llama_cpp_multimodal_resident` mode plus `run_jetson_p6_resident_vlm_smoke.sh`.
- The current accepted claim boundary is no longer "P6-VLM evidence pending": `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` already proves standalone resident VLM on Jetson with `vlm_rows=3`, `vlm_bad_rows=0`, same `resident_server_pid=4611`, `resident_model_load_count=1`, and request index `1/2/3`. The remaining Jetson blocker is the integrated request path inside P7/P8, not standalone worker startup.
- Jetson P6/P7/P8 llama.cpp VLM wrappers now default to a more conservative CPU-first profile: `VLM_NGL=0`, `VLM_NO_KV_OFFLOAD=1`, `VLM_NO_MMPROJ_OFFLOAD=1`, and smaller image/output token budgets. This is deliberate: `-ngl 0` alone does not stop KV cache from landing on GPU, and Jetson current closure goal is “resident worker can complete requests” rather than “maximize VLM answer length”.
- Jetson P7/P8 wrappers now also default `TEXT_DEVICE=none`. This is a targeted concurrency mitigation: standalone Jetson resident text can tolerate CPU execution because `TEXT_MAX_CALLS` is very low, while resident VLM is the part that still needs scarce CUDA capacity. For compatibility with earlier board-side commands, the Project5 resident client also normalizes `TEXT_DEVICE=cpu` to llama.cpp's accepted `--device none`.
- Jetson P7/P8 wrappers now also default `DETECTOR_START_ORDER=after_workers`. This is not a throughput optimization. It exists to separate two different failure classes on Jetson: `resident detector already consumed GPU before VLM startup`, versus `resident VLM still cannot start even when detector has not started yet`.
- After `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v7` and `v8`, Jetson P7/P8 wrappers remain tightened for runtime closure rather than answer richness: `SERVICE_QUEUE_CAPACITY=192`, `TEXT_MAX_TOKENS=64`, `TEXT_TIMEOUT_MS=180000`, `QWEN_NO_THINK=1`, `VLM_MAX_TOKENS=64`, `VLM_TIMEOUT_MS=210000`. `v8` has already proved `window_requirement_met=true` and `drop_count=0`, so the point of these defaults is now to preserve a valid concurrent window while exposing the true remaining blocker: resident VLM request failure (`RemoteDisconnected` / `timeout`), not queue saturation.
- `run_jetson_p7_resident_service_smoke.sh` and `run_jetson_p8_resident_service_required.sh` are still kept as the all-resident diagnostic topology. They are no longer the first Jetson closure path.
- The accepted Jetson formal route is now: `run_jetson_p7_detector_text_resident_smoke.sh` for realtime runtime proof, `run_jetson_p7_route_b_dual_service_smoke.sh` with `ASYNC_LAUNCH_MODE=postrun` for 10-minute dual-lane proof, and `run_jetson_p8_route_b_postrun_required.sh` for the 30-minute required window.
- `20260716_jetson_8gb_alarm_service_route_b_target_v1` and `v2` proved that the accepted Jetson realtime lane could sustain a full 2-hour target window, but the postrun async VLM lane still stalled at `1/2 pass`. The direct runtime evidence was no longer just `RemoteDisconnected`: the first async once request hit `NvMapMemAllocInternalTagged error 12` and `CUBLAS_STATUS_NOT_INITIALIZED` inside `llama-server`, while the second event still passed later in the same postrun lane. `v2` also proved that `ASYNC_POSTRUN_COOLDOWN_SEC=30` plus `VLM_RETRY_BACKOFF_SEC=30` was still not enough.
- The accepted Jetson target is now `20260717_jetson_8gb_alarm_service_route_b_target_v3`. The route-B async worker prewarm knobs, `VLM_ONCE_PREWARM_REQUEST=1` and `VLM_ONCE_PREWARM_MAX_TOKENS=8`, were validated there: realtime lane held `window_sec=7220.025`, `detection_fps=29.989231`, `drop_count=0`, and the postrun async lane reached `async_vlm_rows=2`, `async_vlm_pass_rows=2`, `async_vlm_fallback_rows=0`.

Current stability raw behavior:

- `run_alarm_service.py` now parses `--monitor-log` directly and writes `memory_mb`, `swap_used_mb`, `temperature_c`, and `power_w` into the Project5 service-owned stability raw.
- `run_alarm_stability_window.py` now also recognizes RK3588 monitor lines that already emit `memory_mb=` and `swap_used_mb=` directly, in addition to the older `mem_total_mb` / `mem_available_mb` pattern.

Input modes:

| Option | Meaning | Current acceptance meaning |
|---|---|---|
| `--detector-mode resident_process` + `--detector-command` + `--detector-output` + `--rules` | Start a Project 05 local detector binary/wrapper as a child process, tail its detector JSONL output, and generate Project5 event packages online. | B-plan resident detector entrypoint. This is the only detector input mode that can support `resident_service_smoke/required` after board monitor and real detector binary evidence are present. |
| `--detector-raw` + `--rules` | Replay Project3-style detector JSONL and generate Project5 event packages. | Useful for detector-to-alarm smoke and stability replay. |
| `--events-input` | Consume an existing Project5 event package JSONL, including `keyframe_path` and `roi_paths` assets. | Required for unified service smoke that exercises real VLM on pre-extracted ROI/keyframe assets. |

`--detector-command` is deliberately restricted: it must point to a Project 05 local detector binary or wrapper. The service rejects legacy cross-project runtime commands so final acceptance cannot accidentally depend on old project scripts.

Local implementation smoke:

| run_id | detector mode | output | schema |
|---|---|---|---|
| `20260709_pc_alarm_service_resident_process_smoke_v3` | `resident_process` with Project5 local fake detector | events=3, alarms=3, per-event raw=3, stability raw=1, `status=pass` | four schema checks pass |

See `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md`.
