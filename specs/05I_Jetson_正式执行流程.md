# 05I_Jetson_正式执行流程

## 适用范围

本流程用于在 Jetson 8GB 上执行项目五第一轮正式 smoke 和后续 required run。它把 05A 的分散步骤整理成可直接执行的命令序列，并明确哪些结果可以作为正式证据，哪些只能作为接口联调。

本流程默认生成 post-detector chain 证据：先由项目三 detector 运行或生成 raw，再由项目五脚本完成事件、解释和 Alarm JSON。它不是完整常驻服务验收，也不是 Project5 独立代码边界验收。若要声明在线系统完成，必须继续执行 `projects/05_alarm_system/specs/05K_常驻服务与并发验收规范.md` 和 `projects/05_alarm_system/specs/05L_项目五独立代码库与适配边界规范.md`，证明 DetectorService、事件队列、LLM/VLM worker 和 AlarmSink 在同一持续运行窗口内协同工作，且最终运行入口不直接耦合项目三/四脚本。

当前执行边界：

| 能力 | 当前执行状态 | 是否可作为正式能力证据 |
|---|---|---|
| 项目三 detector raw 接入 | 可执行 | 是，但必须引用项目三 raw/log |
| 事件触发与 event package | 可执行 | 是，schema pass 后可作为项目五事件证据 |
| Qwen3-1.7B 文本解释 template 模式 | 可执行 | 否，只是接口联调 |
| Qwen3-1.7B 文本解释 llama.cpp 模式 | 可执行 | 是，需记录 real model raw/log/timeout |
| Qwen3-VL ROI 复核 | 可执行；Jetson accepted 主线中按 `postrun async VLM enrichment` 使用，旧同窗 resident VLM 只保留诊断 | 是，但仅限低频异步视觉补充；不能写成 Jetson 同窗实时 VLM 已通过 |
| SmolVLM2 视频理解 | 禁用 | 不作为视频模型能力；只记录 fallback |
| alarm JSON / per-event raw / schema check | 可执行 | 是，schema pass 是格式证据，不等于业务质量 pass |
| 30 分钟稳定性 | 已完成 Jetson video playlist required run；camera source 仍需单独执行 | 需要 time-window raw 和 monitor log |
| Project5 本地 resident detector smoke wrapper | 已完成 | 是，Jetson 已通过 `resident_detector_smoke_pass_with_template_stub_workers` |
| Jetson resident text 最小复用 | 已完成 `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` | 是，但只可声明 `resident_text_worker_smoke_pass`，不等于 Jetson 单板 `resident_service_smoke` |
| Jetson resident VLM 最小复用 | 已完成 `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4`：`vlm_rows=3`、`vlm_bad_rows=0`、同一 `resident_server_pid=4611`、`resident_model_load_count=1`、`resident_request_index=1/2/3` | 是，但只可声明 `resident_vlm_worker_smoke_pass`，不等于 Jetson 单板 `resident_service_smoke` |
| resident service | Jetson 单板 accepted 路线已经完成：`resident detector + resident text + postrun async VLM enrichment` 已完成 smoke、required、target；旧同窗 resident VLM request path 只保留诊断 | 是；双板 target 已完成，发布侧 text fact guard 已在 `20260718...v3` 验证 |
| independent Project5 runtime | 已完成 `independent_runtime_pass` | 已由 05L 代码边界检查和 Project5 本地 detector/service 板端 run 验证；Project3 raw replay 不作为该结论的唯一依据 |

所有命令必须使用 `python3`。Jetson 默认 `python` 可能是 Python 2.7，不能用于项目五脚本。

## 当前 Jetson accepted 方案（2026-07-17）

Jetson 单板实验主线已经做完，当前 accepted 方案不再是“三常驻同窗”。原因很直接：`projects/05_alarm_system/scripts/service/run_alarm_service.py` 当前只有一个 `alarm-worker` 线程，单个事件仍按 `asset -> text -> vlm -> alarm` 串行消费；把 resident VLM 强行留在同一实时窗口内，会把问题重新收口到 multimodal request path 并发干扰，而不是提高系统完成度。

因此，Jetson 当前正式方案固定为两条 lane：

1. realtime lane：`resident detector + resident text + VLM stub`
2. async lane：在同一 `RUN_ID` 下，对 realtime lane 已落盘的 `events.jsonl` 执行 `postrun async VLM enrichment`

这里的 `postrun` 不是“另开一个无关 run 手工补做”，而是同一 `RUN_ID`、同一事件集、同一资产来源上的第二阶段低频视觉补充。它的目的就是在不阻塞检测主链路的前提下，把真实 Qwen3-VL 结果补回当前 run 的产物集合。

当前推荐顺序如下：

| 顺序 | 路线 | 目标 | 通过后可声明 | 当前意义 |
|---|---|---|---|---|
| 1 | `P4 detector resident smoke` | 先证明 Project5 本地 detector、规则、队列、AlarmSink | `resident_detector_smoke_pass_with_template_stub_workers` | Jetson 已完成 |
| 2 | `P6 resident text smoke` | 先证明 Qwen3 文本 resident 复用 | `resident_text_worker_smoke_pass` | Jetson 已完成 |
| 3 | `P6 resident VLM smoke` | 先证明 Qwen3-VL resident 复用 | `resident_vlm_worker_smoke_pass` | Jetson 已完成 standalone |
| 4 | `Route B realtime: detector resident + text resident + VLM stub` | 把实时主链路稳定收敛到 detector + text | `route_b_realtime_smoke_pass` | Jetson 已完成 |
| 5 | `Route B dual-service: realtime detector+text + async VLM worker` | 在一个 `RUN_ID` 下先完成 realtime lane，再以同一 `RUN_ID` 做 `postrun` async VLM enrichment | `route_b_dual_service_smoke_pass` | Jetson 已完成并作为 accepted 10 分钟主线 |
| 6 | `Route B required` | 把 accepted 双 lane 主线扩展到 30 分钟 required | `resident_service_required`（Jetson 单板 accepted 路线） | Jetson 已完成 |
| 7 | `Route B target` | 把 accepted 双 lane 主线扩展到 2 小时 target | `resident_service_target`（Jetson 单板 accepted 路线） | 已由 `20260717_jetson_8gb_alarm_service_route_b_target_v3` 完成 |
| 8 | `Route B async enrichment: events_input + VLM resident/once` | 复用 Route B 事件，单独低频补充视觉解释 | `route_b_async_vlm_smoke_pass` | 手工回放/诊断入口 |
| 9 | `Route A / legacy all-resident same-window` | 继续诊断 live detector 下 multimodal request path，或继续复测旧三常驻同窗 | 只作诊断，不是当前默认主线 | 保留旧脚本，不优先 |

也就是说，Jetson 当前正式执行与验收只按下面的 accepted 方案解释：

1. realtime：`detector resident + text resident`
2. low-frequency visual enrichment：`postrun async VLM enrichment`
3. Route A 和 legacy same-window resident VLM：只作诊断，不再阻塞当前正式主线

截至 `2026-07-17`，Jetson 单板 accepted 路线已经完整推进到 `P9 target`。正式通过 run 为 `20260717_jetson_8gb_alarm_service_route_b_target_v3`：

- realtime lane：`window_sec=7220.025`、`requested_window_sec=7200.0`、`window_requirement_met=true`、`detection_fps=29.989231`、`event_count=1550`、`alarm_count=1550`、`drop_count=0`
- resident text：`llm_call_count=2`、`llm_rows=1550`、`llm_pass_rows=2`、同一 `resident_server_pid=1583009`、`resident_model_load_count=1`
- postrun async VLM：`async_vlm_rows=2`、`async_vlm_pass_rows=2`、`async_vlm_fallback_rows=0`、`async_vlm_failed_rows=0`

这意味着 Jetson 当前正式缺口已经不再是“单板 target 能否闭环”，而是：

1. 冻结 `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3`：resident text 原文审计与 Alarm JSON 发布侧事实守卫均已验证。
2. 旧同窗 resident VLM request path 的诊断性复现实验（非主线验收项）

`20260717_p05_dual_board_target_v1` 已完成双板 `P9 target`：Jetson 槽位 `7217.22s / 30.000887 FPS / drop=0`，RK3588 槽位 `7203.72s / 30.042395 FPS / LLM=2 / VLM=2 / drop=0`，启动差 `22.5s`、有效重叠 `7194.72s`，组级状态为 `dual_board_target_ready`。

### Route B 集成双进程执行入口（当前正式主线）

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export DURATION_SEC=600
export TEXT_MAX_CALLS=2
export SERVICE_QUEUE_CAPACITY=64
export ASYNC_VLM_MAX_CALLS=2
export ASYNC_LAUNCH_MODE=postrun
export ASYNC_VLM_REQUIRE_PASS_ROWS=2
export ASYNC_VLM_MODE=llama_cpp_multimodal_once
export ASYNC_STOP_AFTER_BUDGET=1
export ASYNC_IDLE_TIMEOUT_SEC=0
export ASYNC_STARTUP_WAIT_SEC=180
export ASYNC_GRACE_SEC=15
export TEXT_NGL=0
export TEXT_NO_KV_OFFLOAD=1
export TEXT_DEVICE=none
export QWEN_NO_THINK=1
export VLM_TIMEOUT_MS=240000
export VLM_STARTUP_TIMEOUT_MS=240000
export VLM_MAX_TOKENS=96
export VLM_NGL=0
export VLM_NO_KV_OFFLOAD=1
export VLM_NO_MMPROJ_OFFLOAD=1
export VLM_REQUEST_RETRIES=1
export VLM_IMAGE_MIN_TOKENS=512
export VLM_IMAGE_MAX_TOKENS=512
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf

bash projects/05_alarm_system/scripts/service/run_jetson_p7_route_b_dual_service_smoke.sh
```

这条入口的产物分两层：

- 实时主链路产物：
  - `benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl`
- 异步 VLM enrichment 产物：
  - `benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_outputs.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarm_enriched.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_enriched_benchmark.jsonl`

这里的关键点不是“把 VLM 拉回实时 worker”，而是让 VLM 作为第二个 Project5 进程在运行期持续消费新事件。这样 detector + resident text 的实时性不再被 VLM 绑死，同时系统也不需要等整轮结束后再手工二次执行。
当前源码还补齐了 `llama_cpp_multimodal_once` 对 `--vlm-request-retries` 的真实消费，因此 Route B dual-service 里的 async VLM lane 现在默认会在首轮 once 调用失败后再重启临时 `llama-server` 重试 1 次，并把最后一次尝试的 runtime log 单独落盘到 `_retryN.log`。但当前正式验收口径已经不再要求它和 realtime lane 同窗抢资源，而是优先使用 `ASYNC_LAUNCH_MODE=postrun`。

最新板端结果（`20260714_jetson_8gb_alarm_service_route_b_dual_service_smoke_v4`）：

- realtime lane：`window_sec=627.353`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=28.741394`
- `event_count=136`
- `alarm_count=136`
- `llm_call_count=2`
- `vlm_call_count=0`
- `drop_count=0`
- `restart_count=0`
- async worker：`async_vlm_rows=2`
- `async_vlm_pass_rows=1`
- `async_vlm_fallback_rows=1`
- pass 行来自 `vehicle_presence_candidate_000001_frame_2`，`resident_retry_count=0`、`resident_server_pid=503522`、`resident_model_load_count=1`、`resident_request_index=1`，`vlm_total_ms=229011.465`
- fallback 行仍为 `person_presence_candidate_000000_frame_2`，错误已从单纯 `timeout` 收口为 `RemoteDisconnected: Remote end closed connection without response`，且 `once_attempts=2`
- 异步 enriched alarm / enriched benchmark / realtime stability 三类 schema 检查均为 `pass`

结论：B 方案双进程编排已经成立，Route B realtime 持续满足 `drop_count=0`，async worker 生命周期也已稳定；`v4` 进一步证明 Jetson async VLM 的成功行不再依赖 `_retry1.log` 才返回结果，但当前仍只有 `1/2 pass`。剩余问题已经收口为 Jetson multimodal request path 的事件级稳定性，而不是编排层或队列层问题。

最新严格门槛结果（`20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5`）：

- 新增门槛：`ASYNC_VLM_REQUIRE_PASS_ROWS=2`
- realtime lane：`window_sec=649.994`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=27.76641`
- `event_count=136`
- `alarm_count=136`
- `llm_call_count=2`
- `vlm_call_count=0`
- `drop_count=0`
- `llm_pass_rows=2`
- 同一 `llm_resident_server_pids=[709936]`
- `llm_resident_model_load_counts=[1]`
- async lane：`async_vlm_rows=2`
- `async_vlm_pass_rows=1`
- `async_vlm_fallback_rows=1`
- 失败事件仍为 `person_presence_candidate_000000_frame_2`，错误为 `RemoteDisconnected`
- 成功事件仍为 `vehicle_presence_candidate_000001_frame_2`，但这次 pass 落在 `_retry1.log`，`resident_retry_count=1`、`vlm_total_ms=220489.768`
- `20260715_..._v5_alarm_enriched_benchmark.jsonl` 已验证写出当前 `run_id=20260715_jetson_8gb_alarm_service_route_b_dual_service_smoke_v5`
- 由于脚本启用了 `require_pass_rows=2`，最终明确失败：`Route B dual-service async VLM failed: pass_rows=1 < required=2`

这条 `v5` 很重要，因为它把“当前只能做到 `1/2 pass`”从观察现象提升成了脚本级硬判定。也就是说，Jetson 当前已经不是“可能偶发失败”，而是在严格 `2/2` 门槛下稳定复现 `person_presence` 事件的 multimodal request path 失败。

随后做的单事件对照 `20260715_jetson_8gb_async_vlm_person_from_v5_run_v1` 又把边界再收紧了一步：

- 输入事件直接取自 `v5` 中失败的 `person_presence_candidate_000000_frame_2`
- async-only 结果为 `async_vlm_rows=1`
- `async_vlm_pass_rows=1`
- `async_vlm_fallback_rows=0`
- `vlm_total_ms=154961.29`
- `resident_retry_count=0`

这说明 `person_presence` 这条事件本身并不是“单独就跑不通”。当前 Jetson 的主阻塞点已经更具体地收口为：当 `detector + resident text realtime lane` 与 `async VLM enrichment` 同时存在于 Route B 窗口内时，multimodal request path 会受到并发干扰。

随后完成的 `20260715_jetson_8gb_alarm_service_route_b_dual_service_postrun_v1` 已经把这条对照实验跑完。仓库当前已在 `run_jetson_p7_route_b_dual_service_smoke.sh` 中支持 `ASYNC_LAUNCH_MODE=parallel|postrun`。`postrun` 的意义是：

- realtime lane 仍保持 `detector + resident text`
- 事件和文本结果仍写入同一 `RUN_ID`
- 但 async VLM worker 改为在 realtime lane 结束后再自动消费同一批 `events.jsonl`

`postrun_v1` 的板端结果已经给出：

- realtime lane：`window_sec=617.063`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=29.248229`
- `event_count=136`
- `alarm_count=136`
- `drop_count=0`
- `llm_pass_rows=2`
- 同一 `llm_resident_server_pids=[753178]`
- `llm_resident_model_load_counts=[1]`
- async lane：`async_vlm_rows=2`
- `async_vlm_pass_rows=2`
- `async_vlm_fallback_rows=0`
- `async_vlm_failed_rows=0`
- `async_vlm_blocked_rows=0`
- 最终结果：`JETSON_ROUTE_B_DUAL_SERVICE_RESULT=realtime_detector_text_plus_async_vlm_worker_ready`

这说明 Jetson 当前真正不可接受的是“同窗并发下的 multimodal request path 干扰”，而不是“系统内低频 VLM 补充”这条能力本身。因此 Jetson 当前正式主线已经收口为：

1. realtime：`detector resident + resident text + VLM stub`
2. postrun：同一 `RUN_ID` 下的 async VLM enrichment

如果要继续推进 30 分钟 required，应直接使用：

```bash
bash projects/05_alarm_system/scripts/service/run_jetson_p8_route_b_postrun_required.sh
```

该步骤现已由 `20260715_jetson_8gb_alarm_service_route_b_required_v1` 完成，结果如下：

- `window_sec=1818.786`
- `requested_window_sec=1800.0`
- `window_requirement_met=true`
- `stability_tier=required`
- `detection_fps=29.76161`
- `event_count=397`
- `alarm_count=397`
- `drop_count=0`
- `llm_pass_rows=2`
- 同一 `llm_resident_server_pids=[789848]`
- `llm_resident_model_load_counts=[1]`
- `async_vlm_rows=2`
- `async_vlm_pass_rows=2`
- `async_vlm_fallback_rows=0`
- `async_vlm_failed_rows=0`
- 最终结果：`JETSON_P8_ROUTE_B_REQUIRED_RESULT=realtime_detector_text_plus_postrun_async_vlm_required_ready`

因此 05I 当前不再把 Jetson P8 记为“待执行”，而是记为“单板已完成，后续继续推进双板联调与文本语义约束”。

### Route A 执行入口

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export DURATION_SEC=600
export VLM_MAX_CALLS=2
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf

bash projects/05_alarm_system/scripts/service/run_jetson_p7_detector_vlm_resident_smoke.sh
```

Route A 的判定重点：

- `window_requirement_met=true`
- `llm_call_count=0`
- `vlm_call_count=2`
- `vlm_pass_rows=2`
- `resident_model_load_count=1`
- `drop_count=0`

最新板端结果（`20260714_jetson_8gb_alarm_service_detector_vlm_resident_smoke_v1`）：

- `window_sec=676.324`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=26.685435`
- `event_count=136`
- `alarm_count=136`
- `llm_call_count=0`
- `vlm_call_count=2`
- `drop_count=0`
- `vlm_pass_rows=0`
- `vlm_bad_rows=2`

结论：Route A 已证明在 live detector 压力下可以维持有效时间窗，但 resident VLM 两次真实图片请求都 timeout，因此 Route A 当前不能声明通过。

### Route B 实时链路执行入口

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export DURATION_SEC=600
export TEXT_MAX_CALLS=2
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf

bash projects/05_alarm_system/scripts/service/run_jetson_p7_detector_text_resident_smoke.sh
```

Route B realtime 的判定重点：

- `window_requirement_met=true`
- `llm_call_count=2`
- `vlm_call_count=0`
- `llm_pass_rows=2`
- `resident_model_load_count=1`
- `drop_count=0`

最新板端结果（`20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1`）：

- `window_sec=612.872`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=29.448237`
- `event_count=136`
- `alarm_count=136`
- `llm_call_count=2`
- `vlm_call_count=0`
- `drop_count=0`
- `llm_pass_rows=2`
- 同一 `resident_server_pid=343498`
- `resident_model_load_count=1`
- `resident_request_index=1/2`

结论：Route B realtime 的运行时链路已经通过，可以把 Jetson 实时主链路收口为 `detector + resident text + VLM stub`。但本轮抽检也发现第 2 条真实文本解释把 `vehicle_presence/car` 错写成“未佩戴安全帽”，因此它当前只能声明 runtime pass，不能直接声明解释语义 pass。

### Route B 异步 VLM enrichment 执行入口

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v2
export BOARD=jetson_8gb
export SOURCE_RUN_ID=20260714_jetson_8gb_alarm_service_detector_text_resident_smoke_v1
export EVENTS_INPUT=benchmark/raw/05_alarm_system/${BOARD}/events/${SOURCE_RUN_ID}_events.jsonl
export MAX_EVENTS=3
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf
export ASSET_SOURCE_TYPE=video_playlist
export ASSET_SOURCE_URI=data/videos/runtime_playlist_v1.txt
export VLM_MAX_CALLS=2
export VLM_MODE=llama_cpp_multimodal_once
export VLM_REQUEST_RETRIES=1
export VLM_TIMEOUT_MS=240000
export VLM_STARTUP_TIMEOUT_MS=240000
export ASYNC_REQUIRE_PASS_ROWS=0

bash projects/05_alarm_system/scripts/service/run_jetson_p7_vlm_async_enrichment_smoke.sh
```

这一步现在直接调用 `projects/05_alarm_system/scripts/service/run_async_vlm_enrichment.py`，不再误走 `run_alarm_service.py`。也就是说：

- `EVENTS_INPUT` 是只读源事件包，wrapper 不会再为当前 `RUN_ID` 生成一个新的 `events.jsonl`
- 产物改为 async 专用命名：
  - `benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_async_vlm_outputs.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarm_enriched.jsonl`
  - `benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_enriched_benchmark.jsonl`
  - `benchmark/processed/05_alarm_system/${RUN_ID}_async_vlm_summary.md`
- 这条入口不再伪造新的 `alarm_system_stability.jsonl`；它是异步诊断/补充解释入口，不是新的实时窗口 run

这一步默认只处理少量事件，并且只为真实 VLM 调用生成少量 keyframe/ROI 资产，不再保留整窗 JPG。当前默认把 async-only 的 `VLM_TIMEOUT_MS` / `VLM_STARTUP_TIMEOUT_MS` 提高到 `240000`，因为 `v3` 里第一条真实 pass 已经用掉了 `177413.336 ms`，继续维持 `180000 ms` 会让低频 enrichment 长期贴着上限运行。`ASYNC_REQUIRE_PASS_ROWS=0` 表示这条入口默认用于诊断，不因为单条 VLM fallback 就立即把整次回放判成脚本失败；若想把单事件诊断强制收敛为“必须至少 1 条真实 pass”，可改成 `ASYNC_REQUIRE_PASS_ROWS=1`。

历史结果 `20260714_jetson_8gb_alarm_service_vlm_async_enrichment_smoke_v1` 仍然保留为“Jetson resident VLM timeout 可在第二条 service run 中独立复现”的证据，但它属于旧 wrapper 产物。当前源码口径已经改成直接消费 `events_input` 并输出 async 专用结果。

2026-07-15 的两次单事件诊断提供了完整对照：

- `20260715_jetson_8gb_async_vlm_person_diag_run_v1` 已拿到 `vlm_call_count=1`、`vlm_pass_rows=1`、`vlm_total_ms=157961.52` 的真实 person VLM pass，但板端输出仍是旧式 `events=/llm=/vlm=/alarms=/benchmark=/stability=`，说明那次板端实际执行的还是旧 wrapper。
- `20260715_jetson_8gb_async_vlm_person_diag_run_v2` 则已经出现 `async_entrypoint=run_async_vlm_enrichment.py`、`async_vlm_output=...`、`async_alarm_output=...`、`async_benchmark_output=...`，并给出 `async_vlm_rows=1`、`async_vlm_pass_rows=1`、`async_alarm_rows=1`、`async_benchmark_rows=1`。这说明新 wrapper 已经真实同步到 Jetson 板端。

如果你在 Jetson 上重新同步了新脚本，启动阶段应该能直接看到：

- `async_entrypoint=run_async_vlm_enrichment.py`
- 结束阶段打印 `async_vlm_output=...`
- 结束阶段打印 `async_alarm_output=...`
- 结束阶段打印 `async_benchmark_output=...`

如果仍然看到旧式 `events=... alarms=... benchmark=... stability=...` 汇总，就说明板端还没同步到最新 wrapper。

另外，`20260715_jetson_8gb_async_vlm_person_diag_run_v2_async_vlm_outputs.jsonl` 已经证明：同一文件若用 Python 按 `utf-8` 直接读取，`vlm_summary` / `vlm_raw_output` 是正常中文；先前看到的“乱码”来自宿主显示/同步链路，而不是 JSONL 文件本身损坏。因此后续 Jetson async VLM 文本验收，必须优先使用 `python3/json` 或支持 UTF-8 的编辑器读取文件，不要只靠同步后的 shell paste 判断。

结论不变：即使把 resident text 从实时链路中彻底拆掉，Jetson 的 `events_input + VLM enrichment` 仍然要继续单独观察真实图片请求是否稳定 pass。因此 Jetson 当前 resident VLM 的主阻塞点仍然是 multimodal request path 本身，而不是 resident text 干扰。

## 0. 统一变量

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260705_jetson_8gb_alarm_system_text_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline

mkdir -p \
  benchmark/raw/05_alarm_system/${BOARD}/events \
  benchmark/raw/05_alarm_system/${BOARD}/alarms \
  benchmark/processed/05_alarm_system \
  logs/runtime/05_alarm_system/${BOARD} \
  logs/benchmark/05_alarm_system/${BOARD} \
  logs/monitor/05_alarm_system/${BOARD} \
  logs/failures/05_alarm_system/${BOARD}
```

## 1. 前置检查

```bash
python3 --version
test -s projects/05_alarm_system/configs/event_rules/jetson_rules.yaml
test -s projects/05_alarm_system/configs/models/jetson_model_combo.yaml
test -s benchmark/schemas/alarm_event_package_schema.json
test -s projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json
test -s benchmark/schemas/alarm_system_raw_schema.json
```

如果要执行真实 Qwen3 文本解释，还必须设置：

```bash
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf

test -x "${LLAMA_BIN}"
test -s "${QWEN3_GGUF}"
script --version
```

## 2. 准备项目三检测输入

优先复用项目三正式 detector raw，但不能假设 Project5 `RUN_ID` 一定对应同名 Project3 raw。先列出 Jetson 上真实存在的 detector raw，再显式选择 `PROJECT3_RAW`。

```bash
find benchmark/raw/03_video_pipeline/jetson_8gb \
  -maxdepth 1 \
  -type f \
  -name "*detector*.jsonl" \
  -printf "%s %p\n" | sort -nr | head -20

export PROJECT3_SOURCE_RUN_ID=20260704_jetson_8gb_alarm_system_smoke_v1
export PROJECT3_RAW=benchmark/raw/03_video_pipeline/jetson_8gb/${PROJECT3_SOURCE_RUN_ID}_detector.jsonl

test -s "${PROJECT3_RAW}" && echo "PROJECT3_RAW exists" || echo "PROJECT3_RAW missing"
```

如果 `PROJECT3_RAW missing`，不要继续执行第 3 步。必须先换成 `find` 中存在的 detector raw，或执行项目三 Jetson pipeline 生成 frame-level detection JSONL。项目五不把空 adapter 或手写 JSON 当成真实检测证据。

如果补 10 分钟准实时 detector run 时，项目三 app 显示 `app_exit=0`、raw 已生成、trace/aggregate 通过，但 `schema_exit=1` 且错误为 `input_source_type='video_playlist' not in allowed set ...`，说明 Jetson 上的 `benchmark/schemas/video_pipeline_raw_schema.yaml` 不是最新版本。当前项目三脚本长期使用 `INPUT_SOURCE_TYPE=video_playlist`，schema 必须允许 `video_playlist`。此时不要重跑 detector，先同步最新 schema 后重做 schema 校验：

```bash
python3 projects/03_video_pipeline/scripts/benchmark/validate_pipeline_raw_schema.py \
  --input benchmark/raw/03_video_pipeline/jetson_8gb/${STABILITY_RUN_ID}.jsonl \
  --schema benchmark/schemas/video_pipeline_raw_schema.yaml \
  --output benchmark/processed/03_video_pipeline/${STABILITY_RUN_ID}_schema_check.md

cat benchmark/processed/03_video_pipeline/${STABILITY_RUN_ID}_schema_check.md
```

只有项目三 schema check 为 `pass` 后，才把该 raw 作为项目五 detector 输入继续执行。

## 2B. 可选摄像头输入分支：继承项目三 IMX219 live-source

如果目标是补 Jetson 摄像头端项目五证据，不要从项目五脚本直接读 `/dev/video0`。项目五当前 detector adapter 的输入是项目三 frame-level detector raw，因此必须先用项目三 camera source 生成 detector raw，再回到本文件第 3 步。

当前可继承的 Jetson 摄像头主线是项目三 `imx219_csi_001`：

| field | value |
|---|---|
| source id | `imx219_csi_001` |
| source type | `mipi_camera` |
| device | `/dev/video0` |
| capture path | V4L2 raw RG10 Bayer -> normalize/debayer -> YOLO11n TensorRT |
| source config | `projects/03_video_pipeline/configs/streams/video_fixed_v1.yaml` |
| implementation | `projects/03_video_pipeline/src/video_pipeline_app.cpp` |
| Project5 status | source inherited; Project5 camera alarm chain pending until new run exists |

项目四不包含摄像头实时 pipeline；它只提供 Qwen3/Qwen3-VL 准入和 SmolVLM2 视频禁用结论。摄像头采集与实时检测必须继承项目三。

建议先执行短时 smoke，再执行 30 分钟 required：

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export CAMERA_RUN_ID=20260708_jetson_8gb_alarm_system_camera_imx219_smoke_v1
export INPUT_SOURCE_ID=imx219_csi_001
export INPUT_SOURCE_TYPE=mipi_camera
export INPUT_PATH=/dev/video0
export DURATION_SEC=600
export LOOP_VIDEO_FILE=0
export PACE_VIDEO_FILE=0
export SAVE_OUTPUT_VIDEO=0
export PREVIEW_WINDOW=off
export V4L2_RAW=1
export V4L2_WIDTH=1920
export V4L2_HEIGHT=1080
export V4L2_SENSOR_MODE=2
export V4L2_FPS=30
export BAYER_PATTERN=RG
export V4L2_NORMALIZE_MODE=percentile
export V4L2_DISABLE_WHITE_BALANCE=0

# 使用项目三 Jetson TensorRT C++ pipeline 入口生成 frame-level detector raw。
# 具体 wrapper 以项目三 runbook 为准；完成后必须得到：
# benchmark/raw/03_video_pipeline/jetson_8gb/${CAMERA_RUN_ID}.jsonl
```

如果板端已有项目三 wrapper，应优先使用项目三 runbook 中 IMX219 live-source 命令，不要手写 C++ app 参数。运行结束后必须补三项后检查：

```bash
python3 projects/03_video_pipeline/scripts/benchmark/validate_pipeline_raw_schema.py \
  --input benchmark/raw/03_video_pipeline/jetson_8gb/${CAMERA_RUN_ID}.jsonl \
  --schema benchmark/schemas/video_pipeline_raw_schema.yaml \
  --output benchmark/processed/03_video_pipeline/${CAMERA_RUN_ID}_schema_check.md

python3 projects/03_video_pipeline/scripts/benchmark/check_pipeline_trace.py \
  --raw benchmark/raw/03_video_pipeline/jetson_8gb/${CAMERA_RUN_ID}.jsonl \
  --output benchmark/processed/03_video_pipeline/${CAMERA_RUN_ID}_trace_check.md

cat benchmark/processed/03_video_pipeline/${CAMERA_RUN_ID}_schema_check.md
cat benchmark/processed/03_video_pipeline/${CAMERA_RUN_ID}_trace_check.md
```

通过后设置：

```bash
export RUN_ID=${CAMERA_RUN_ID}
export PROJECT3_RAW=benchmark/raw/03_video_pipeline/jetson_8gb/${CAMERA_RUN_ID}.jsonl
```

然后继续执行第 3-9 步。正式报告中必须把 `input_source_id=imx219_csi_001`、`input_source_type=mipi_camera`、camera runtime log、Project3 schema/trace check 和 Project5 event/alarm schema check 一起记录。没有这组证据时，不能写成“项目五摄像头告警系统通过”。

Argus 路线 `imx219_csi_argus_001` 在项目三已记录为当前板端 probe failed，不得作为项目五 pass 路线；RTSP/USB 也必须先完成项目三 source probe 和 detector raw，再进入项目五。

## 3. 接入检测 raw

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_detector_adapter.py \
  --board-config projects/05_alarm_system/configs/boards/jetson_8gb.yaml \
  --source projects/03_video_pipeline/configs/streams/video_fixed_v1.yaml \
  --project3-config projects/03_video_pipeline/configs/pipeline/jetson_tensorrt_pipeline.yaml \
  --project3-raw "${PROJECT3_RAW}" \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_detector_events.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_detector_adapter.log 2>&1

wc -l benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_detector_events.jsonl
cat logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_detector_adapter.log
```

## 4. 生成 Event Package

正式规则必须生成 `alarm_domain=visual_detection`，且 `alarm_type` 只能是 `person_presence`、`vehicle_presence`、`multi_object_scene`。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_event_trigger.py \
  --detections benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_detector_events.jsonl \
  --rules projects/05_alarm_system/configs/event_rules/jetson_rules.yaml \
  --run-id "${RUN_ID}" \
  --output benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_event_trigger.log 2>&1

cat logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_event_trigger.log
wc -l benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_event_package_schema_check.md

cat benchmark/processed/05_alarm_system/${RUN_ID}_event_package_schema_check.md
```

事件类型统计：

```bash
python3 - <<'PY'
import json
from collections import Counter
path = f"benchmark/raw/05_alarm_system/jetson_8gb/events/{__import__('os').environ['RUN_ID']}_events.jsonl"
c = Counter()
with open(path, encoding="utf-8") as f:
    for line in f:
        if line.strip():
            row = json.loads(line)
            c[(row.get("alarm_domain"), row.get("alarm_type"))] += 1
print(c)
PY
```

## 5A. 接口 smoke：template 文本解释

这一步只验证 alarm JSON 链路，不是 Qwen3 真实性能证据。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_llm_explain.py \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --mode template \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llm_explain.log 2>&1
```

## 5B. 真实文本 smoke：Qwen3 llama.cpp thinking 模式

这一步才可作为真实 Qwen3 文本解释证据。Jetson 当前 `llama-cli` 生成后会进入交互提示符，且部分版本会把生成内容写到交互 TTY 而不是普通 stdout/stderr；项目五脚本必须使用新版 `script` 会话捕获逻辑，并默认追加 `--single-turn`，避免停在第一条事件后等待交互退出。thinking 模式需要更大的输出预算，当前实测 `--ctx 2048 --max-tokens 768 --timeout-ms 120000` 可以完成 10 条事件。

正式执行前先清理旧失败产物，避免把旧的空 `llm_raw_output` 混入本轮证据：

```bash
rm -f benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl
rm -rf logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_sessions
```

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_llm_explain.py \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --mode llama_cpp \
  --llama-bin "${LLAMA_BIN}" \
  --model-path "${QWEN3_GGUF}" \
  --ctx 2048 \
  --max-tokens 768 \
  --ngl 99 \
  --timeout-ms 120000 \
  --capture-mode script \
  --session-log-dir logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_sessions \
  --max-events 10 \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llm_explain.log 2>&1

cat logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llm_explain.log

python3 - <<'PY'
import json, os, sys
path = f"benchmark/raw/05_alarm_system/{os.environ['BOARD']}/{os.environ['RUN_ID']}_llm_outputs.jsonl"
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
bad = [row for row in rows if row.get("status") != "pass" or not row.get("llm_explanation")]
print(f"llm_rows={len(rows)}")
print(f"llm_bad_rows={len(bad)}")
if rows:
    first = rows[0]
    print("first_status=", first.get("status"))
    print("first_thinking_included=", first.get("thinking_included"))
    print("first_llm_explanation=", (first.get("llm_explanation") or "")[:300])
    print("first_has_raw=", bool(first.get("llm_raw_output")))
    print("first_capture_mode=", first.get("capture_mode"))
    print("first_session_log_path=", first.get("session_log_path"))
if bad:
    print("bad_event_ids=", [row.get("event_id") for row in bad[:5]])
    sys.exit(1)
PY
```

如果出现 `request (...) exceeds the available context size`，说明输入 prompt 加事件 JSON 超过 `--ctx`，应优先增大 `--ctx`，不是增大 `--max-tokens`。如果日志停在 `>` 且没有进入下一条事件，说明板端脚本不是最新版本；新版脚本会自动追加 `--single-turn`。如果终端日志能看到模型输出，但 JSON 中 `llm_raw_output=None` 或 `llm_explanation=None`，必须检查 `first_capture_mode` 是否为 `script`，以及 `first_session_log_path` 指向的会话日志是否包含 `[End thinking]` 后四行结果；如果没有，说明板端脚本或 `script` 命令未同步成功，本 LLM run 必须作废重跑。当前 Jetson llama.cpp b9777 的 `llama-cli` 不支持 `--no-conversation`，新版脚本会兼容接收该参数但不会转发给 `llama-cli`；如果 `llm_explanation` 出现 `--no-conversation is not supported by llama-cli`，该 LLM run 必须作废并从本步骤重跑。如果日志出现 `[Start thinking]`，这是 thinking 模式预期行为；脚本会把 `[End thinking]` 后的最终四行写入 `llm_explanation`，并把完整原始输出保存在 `llm_raw_output`。如果 `llm_rows` 正确但 `llm_bad_rows>0`，不能继续生成 Alarm JSON，必须先修复 LLM 输出。schema pass 不能替代 LLM 内容检查。如果出现 timeout、OOM、CUDA 初始化失败或输出为空，本 run 不能写成真实文本解释通过，必须进入 `failure_and_fallback.md` 和 `troubleshooting.md`。

### 5C. 统一 service 入口：真实文本 single-shot worker

这一步使用 Project5 本地 service 入口统一调度 replay detector、event queue、LLM worker、VLM stub 和 AlarmSink。它比前面的分散命令更接近最终系统，但仍然不是 resident service：detector 来自 Project3 raw replay，LLM 是 single-shot `llama-cli` 调用，VLM 仍为 stub。

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab
export RUN_ID=20260709_jetson_8gb_alarm_service_llama_worker_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export PROJECT3_RAW=benchmark/raw/03_video_pipeline/jetson_8gb/20260704_jetson_8gb_alarm_system_smoke_v1_detector.jsonl
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf

python3 projects/05_alarm_system/scripts/service/run_alarm_service.py \
  --run-id "${RUN_ID}" \
  --board "${BOARD}" \
  --board-name "Jetson 8GB" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --detector-raw "${PROJECT3_RAW}" \
  --rules projects/05_alarm_system/configs/event_rules/jetson_rules.yaml \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --max-events 3 \
  --queue-capacity 8 \
  --stability-tier smoke \
  --window-sec 600 \
  --text-mode llama_cpp \
  --text-model-path "${QWEN3_GGUF}" \
  --llama-bin "${LLAMA_BIN}" \
  --text-ctx 2048 \
  --text-max-tokens 768 \
  --text-timeout-ms 120000 \
  --text-max-calls 3 \
  --capture-mode script \
  --session-log-dir logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_sessions \
  --vlm-mode stub \
  --vlm-max-calls 0 \
  2>&1 | tee logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_service_stdout.log
```

统一入口运行后必须验证四类输出：

```bash
python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --schema benchmark/schemas/alarm_event_package_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_service_event_schema_check.md

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_service_alarm_schema_check.md

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_service_raw_schema_check.md

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_service_stability_schema_check.md
```

如果 `llm_call_count` 小于 `--text-max-calls`、`fallback_status.llm=template_fallback`、或 `llm_explanation` 为空，本 run 不能写成真实 LLM service smoke pass。即使 schema pass，也只能写成 service wiring 或 fallback smoke。

### 5D. 可选：no-think 生产化对照

如果目标是稳定生产 Alarm JSON，而不是评估模型思考质量，可以使用 no-think 路线。该路线更短、更快，但需要板端脚本包含 `--qwen-no-think` 参数。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_llm_explain.py \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --mode llama_cpp \
  --llama-bin "${LLAMA_BIN}" \
  --model-path "${QWEN3_GGUF}" \
  --ctx 1536 \
  --max-tokens 128 \
  --ngl 99 \
  --timeout-ms 30000 \
  --capture-mode script \
  --session-log-dir logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llama_sessions \
  --qwen-no-think \
  --max-events 10 \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_llm_explain.log 2>&1
```

## 5E. Jetson P4：Project5 本地 resident detector 10 分钟 smoke

这一步是 Jetson 当前可以立即推进的常驻主线。它不再复用 Project3 raw replay，而是直接启动 Project5 本地 TensorRT detector binary，在 600 秒窗口内持续生成 detector JSONL、event package、Alarm JSON、per-event raw 和 stability raw。为了先隔离 detector、队列和 AlarmSink，本步骤固定 `template` + `stub`，要求 `llm_call_count=0`、`vlm_call_count=0`。

先在 Jetson 板端编译 Project5 本地 detector runner：

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

RUN_ID=20260713_jetson_8gb_p05_detector_build_v1 \
  bash projects/05_alarm_system/scripts/build/build_jetson_detector_service.sh
```

再执行正式 P4 wrapper：

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export DURATION_SEC=600
export DETECTOR_STARTUP_TIMEOUT_SEC=90

bash projects/05_alarm_system/scripts/service/run_jetson_p4_resident_detector_smoke.sh
```

通过条件：

- `SERVICE_EXIT=0`，且实际墙钟运行不短于 `600s`。
- `requested_window_sec=600.0`、`window_sec>=600`、`window_requirement_met=true`。
- `llm_call_count=0`、`vlm_call_count=0`。
- event/alarm/per-event/stability 四类 schema 全部 pass。
- `logs/monitor/05_alarm_system/jetson_8gb/<run_id>_tegrastats.log` 非空。

如果板端日志报 `resident detector did not create output within 10.0s`，说明不是规则或队列错误，而是 Jetson TensorRT detector 冷启动超过默认就绪等待。当前 wrapper 已支持 `DETECTOR_STARTUP_TIMEOUT_SEC` 环境变量，正式重跑时优先放宽到 `90` 或 `120` 秒，而不是改 `DURATION_SEC`。

已验证结果：

| run_id | resident detector rows | window_sec | detection_fps | events | alarms | llm_call_count | vlm_call_count | queue_depth | drop_count | schema | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` | 18048 | 612.629 | 29.458286 | 136 | 136 | 0 | 0 | 3 | 0 | event/alarm/per-event/stability 全部 pass | `resident_detector_smoke_pass_with_template_stub_workers` |

这一步通过后，只能声明 `resident_detector_smoke_pass_with_template_stub_workers`。它还不能声明 Jetson resident text、Jetson resident VLM 或最终 `resident_service_required`。

Jetson P6 text smoke 已完成，Jetson P6 resident VLM smoke 也已在 `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 通过：Project5 通过 `--text-mode llama_cpp_resident` / `--vlm-mode llama_cpp_multimodal_resident` 在 service 启动时拉起本地 `llama-server`，并通过 HTTP 在同一 pid 内处理多次事件请求，记录 `resident_server_pid`、`resident_model_load_count` 和 `resident_request_index`。因此当前下一步已经从“补 Jetson resident VLM 代码”推进到“收口 Jetson P7 并发窗口中的 VLM request path，再进入 Jetson P8”。

## 5F. Jetson P6：Project5 本地 resident text 最小复用 smoke

这一步不再验证 detector 常驻，而是复用已经过 schema 校验的 Project5 event package，单独证明 Jetson 文本解释 worker 已经具备“一次加载，多次请求复用”的 Project5 本地 resident 能力。它的通过口径是：

- `run_alarm_service.py --text-mode llama_cpp_resident` 成功启动本地 `llama-server`。
- `benchmark/raw/05_alarm_system/..._llm_outputs.jsonl` 中真实 `pass` 行保持同一 `resident_server_pid`。
- 所有真实 `pass` 行的 `resident_model_load_count=1`。
- `resident_request_index` 单调递增。
- event/alarm/per-event/stability 四类 schema 全部 pass。

执行前准备：

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260713_jetson_8gb_alarm_service_resident_text_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export EVENTS_INPUT=benchmark/raw/05_alarm_system/${BOARD}/events/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_events.jsonl
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf

test -s "${EVENTS_INPUT}"
test -x "${LLAMA_BIN}"
test -s "${QWEN3_GGUF}"
```

正式执行：

```bash
bash projects/05_alarm_system/scripts/service/run_jetson_p6_resident_text_smoke.sh
```

如需显式指定 `llama-server` 路径，可以额外设置：

```bash
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
```

已验证结果：

| run_id | window_sec | events | alarms | llm_rows | llm_bad_rows | resident_server_pid | resident_model_load_count | resident_request_index | 结论 |
|---|---:|---:|---:|---:|---:|---|---:|---|---|
| `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` | 74.571 | 3 | 3 | 3 | 0 | `3828920` | 1 | `1/2/3` | `resident_text_worker_smoke_pass` |

通过后只可声明：

- `resident_text_worker_smoke_pass`

仍不可声明：

- Jetson resident VLM 板端 smoke 已通过
- Jetson 单板 `resident_service_smoke`
- Jetson 单板 `resident_service_required`

## 5G. Jetson P6：Project5 本地 resident VLM 最小复用 smoke

这一步复用已通过 schema 校验的 Jetson Project5 event package，不再要求你先手工构造 `events_with_assets`。Project5 service 会在同一次 run 内根据 `frame_id` 和 `roi_boxes`，从 `video_set_runtime_v1` 对应的 `video_playlist` 回填 keyframe/ROI 资产，然后用本地 multimodal `llama-server` 复用同一进程处理多次图片请求。

执行前准备：

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v1
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export EVENTS_INPUT=benchmark/raw/05_alarm_system/${BOARD}/events/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_events.jsonl
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf

test -s "${EVENTS_INPUT}"
test -x "${LLAMA_BIN}"
test -x "${LLAMA_SERVER_BIN}"
test -s "${QWEN3_VL_GGUF}"
test -s "${QWEN3_VL_MMPROJ}"
```

正式执行：

```bash
bash projects/05_alarm_system/scripts/service/run_jetson_p6_resident_vlm_smoke.sh
```

当前 P6 standalone wrapper 已回到项目四 selected 路线的单模型默认值：`VLM_NGL=8`、`VLM_NO_KV_OFFLOAD=0`、`VLM_NO_MMPROJ_OFFLOAD=0`、`VLM_TIMEOUT_MS=120000`。这一步的目标是先验证“单独 resident VLM 能否一次加载后处理多次图片请求”，因此默认值和 P7/P8 并发窗口不同。Jetson 单板 P7/P8 为了先保 detector，会继续使用更保守的并发默认值：`TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`。

通过口径：

- `benchmark/raw/05_alarm_system/..._vlm_outputs.jsonl` 中真实 `pass` 行保持同一 `resident_server_pid`
- `resident_model_load_count=1`
- `resident_request_index` 单调递增
- 事件、Alarm、per-event raw、stability raw 四类 schema 全部 pass

这一步通过后，只能声明：

- `resident_vlm_worker_smoke_pass`

它仍然不能替代：

- Jetson 单板 `resident_service_smoke`
- Jetson 单板 `resident_service_required`

并发说明：

- `resident_vlm_smoke` 现在已经可以写成通过。`20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已记录 `vlm_rows=3`、`vlm_bad_rows=0`、同一 `resident_server_pid=4611`、`resident_model_load_count=1`、请求序号 `1/2/3`，因此当前 Jetson 的问题不再是 standalone resident VLM 能否成立，而是并发窗口里的 request path 能否稳定通过。
- 如果板端 server log 仍出现 `n_parallel is set to auto, using n_parallel = 4`，说明板端没有同步到最新 Project5 resident client 代码；当前仓库已固定 resident llama.cpp text/VLM client 使用 `-np 1`，并会把 `parallel`、`ngl`、`no_kv_offload` 等参数写入 service log。
- 但进入 Jetson 单板 P7/P8 时，resident detector、resident text 和 resident VLM 会同时占用板端资源；若继续沿用激进的 GPU/MMProj 默认值，可能在 VLM server 启动阶段直接触发 `cudaMalloc failed: out of memory`。
- 因此，Jetson P7/P8 wrapper 已收敛为保守默认：`TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`。`-ngl 0` 只关闭模型层 offload，并不自动关闭 KV cache offload；这里额外关闭 text/VLM 的 KV cache GPU 放置，再关闭 VLM 的 mmproj offload，优先保证 detector、text、VLM 三者可共存，再验证检测链路不被阻塞。

## 6. VLM 路由记录

当前项目五脚本只记录 Qwen3-VL ROI 路由，不执行真实 VLM。原因是 event package 还没有真实 `roi_paths` 图片资产。此步骤只能作为接口证据。

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_vlm_roi_qa.py \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --max-events 3 \
  --timeout-ms 45000 \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_vlm_roi_qa.log 2>&1
```

正式报告中必须写：`Qwen3-VL route recorded; not model execution`。不能把它写成 Qwen3-VL 项目五性能。

## 7. 生成 Alarm JSON

```bash
python3 projects/05_alarm_system/scripts/run_demo/build_alarm_json.py \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --llm benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl \
  --vlm benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl \
  --video none \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --output benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl \
  > logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_alarm_json.log 2>&1

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl \
  --schema projects/05_alarm_system/configs/alarm_schema/alarm_event_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_alarm_json_schema_check.md

cat benchmark/processed/05_alarm_system/${RUN_ID}_alarm_json_schema_check.md
```

## 8. 生成 per-event benchmark raw

```bash
python3 projects/05_alarm_system/scripts/benchmark/run_alarm_system_benchmark.py \
  --board "${BOARD}" \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --alarms benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl \
  > logs/benchmark/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.log 2>&1

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_benchmark.jsonl \
  --schema benchmark/schemas/alarm_system_raw_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_raw_schema_check.md

cat benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_raw_schema_check.md
```

## 9. 生成 time-window stability raw

当前文本 smoke 如果没有 monitor，只能生成 `not_verified` stability raw，用于证明“稳定性证据缺口已经被结构化记录”，不能作为稳定性 pass。

```bash
python3 projects/05_alarm_system/scripts/benchmark/run_alarm_stability_window.py \
  --run-id "${RUN_ID}" \
  --board "Jetson 8GB" \
  --target "${BOARD}" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --input-source-id video_set_runtime_v1 \
  --stability-tier smoke \
  --window-sec 600 \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${RUN_ID}_events.jsonl \
  --alarms benchmark/raw/05_alarm_system/${BOARD}/alarms/${RUN_ID}_alarms.jsonl \
  --llm benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_llm_outputs.jsonl \
  --vlm benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_vlm_outputs.jsonl \
  --runtime-log-path logs/runtime/05_alarm_system/${BOARD}/${RUN_ID}_alarm_json.log \
  --status not_verified \
  --service-status unknown \
  --output benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl \
  2>&1 | tee logs/benchmark/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.log

python3 projects/05_alarm_system/scripts/benchmark/validate_alarm_jsonl.py \
  --input benchmark/raw/05_alarm_system/${BOARD}/${RUN_ID}_alarm_system_stability.jsonl \
  --schema benchmark/schemas/alarm_system_stability_schema.json \
  --output benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_stability_schema_check.md

cat benchmark/processed/05_alarm_system/${RUN_ID}_alarm_system_stability_schema_check.md
```

如果要执行 10 分钟 stability smoke，必须同时采集 `tegrastats`：

```bash
export STABILITY_RUN_ID=20260707_jetson_8gb_alarm_system_stability_smoke_v1
export MONITOR_LOG=logs/monitor/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_tegrastats.log

rm -f "${MONITOR_LOG}"
tegrastats --interval 1000 > "${MONITOR_LOG}" 2>&1 &
export TEGRASTATS_PID=$!

# 在这里执行本文件第 3-8 步，RUN_ID 使用 ${STABILITY_RUN_ID}。
# 完成后停止 monitor。

kill "${TEGRASTATS_PID}"
wait "${TEGRASTATS_PID}" 2>/dev/null || true

python3 projects/05_alarm_system/scripts/benchmark/run_alarm_stability_window.py \
  --run-id "${STABILITY_RUN_ID}" \
  --board "Jetson 8GB" \
  --target "${BOARD}" \
  --environment-baseline-id "${ENV_BASELINE_ID}" \
  --model-config projects/05_alarm_system/configs/models/jetson_model_combo.yaml \
  --input-source-id video_set_runtime_v1 \
  --stability-tier smoke \
  --window-sec 600 \
  --events benchmark/raw/05_alarm_system/${BOARD}/events/${STABILITY_RUN_ID}_events.jsonl \
  --alarms benchmark/raw/05_alarm_system/${BOARD}/alarms/${STABILITY_RUN_ID}_alarms.jsonl \
  --llm benchmark/raw/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_llm_outputs.jsonl \
  --vlm benchmark/raw/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_vlm_outputs.jsonl \
  --monitor-log "${MONITOR_LOG}" \
  --runtime-log-path logs/runtime/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_alarm_json.log \
  --status not_verified \
  --service-status running \
  --output benchmark/raw/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_alarm_system_stability.jsonl \
  2>&1 | tee logs/benchmark/05_alarm_system/${BOARD}/${STABILITY_RUN_ID}_alarm_system_stability.log
```

30 分钟 required run 必须把 `--stability-tier required` 和 `--window-sec 1800` 写入 raw，并在 `stability_report.md` 中回填资源峰值、fallback/error/restart/reconnect。

## 10. 最小结果判定

| 条件 | run 状态 |
|---|---|
| 三类 schema 全部 pass，但 LLM 是 template、VLM 是 stub、无 monitor | `not_verified_interface_smoke` |
| 三类 schema 全部 pass，LLM 为真实 Qwen3 llama.cpp，VLM 是 stub、无 monitor | `not_verified_text_model_smoke` |
| 三类 schema 全部 pass，LLM 为真实 Qwen3，monitor 存在，检测未明显退化，但无 30 分钟稳定性 | `not_verified_system_smoke` |
| 30 分钟 required run 有 time-window raw、monitor、fallback/error 记录，检测不被阻塞 | 可评估 `pass` 或 `degraded` |
| 任一 schema fail、event_id 不可追溯、LLM 输出改写检测事实 | `fail`，必须进问题库 |

## 11. 执行后必须回填

| 文件 | 回填内容 |
|---|---|
| `projects/05_alarm_system/runs/${RUN_ID}/run.md` | 命令、状态、输入输出、schema、日志、问题 |
| `projects/05_alarm_system/reports/event_pipeline.md` | event count、alarm_domain/alarm_type 分布、schema check |
| `projects/05_alarm_system/reports/llm_vlm_benchmark.md` | LLM mode、rows、total_ms、tokens/s、timeout、VLM stub 状态 |
| `projects/05_alarm_system/reports/alarm_system_benchmark.md` | per-event raw、schema pass、e2e latency、fallback |
| `projects/05_alarm_system/reports/failure_and_fallback.md` | timeout/OOM/JSON fail/视频禁用/VLM stub |
| `projects/05_alarm_system/reports/troubleshooting.md` | 新问题或已知风险回归 |

## 12. 当前不能写成完成的内容

- 不能把 template LLM 写成 Qwen3-1.7B 真实运行。
- 不能把 `run_vlm_roi_qa.py` 的 stub 写成 Qwen3-VL 真实运行。
- 不能把 542 条旧 `generic_object_event` 写成正式告警。
- 没有 30 分钟 time-window stability raw 时，不能写成项目五稳定性通过。
- 没有人工固定事件集时，不能计算误报率、召回率或 verified alarm rate。
## 2026-07-13 Jetson 收口增量

Jetson 当前不是单一“显存不够”问题，而是两条独立阻塞链：

| issue | 当前现象 | 当前收口动作 |
|---|---|---|
| `P05-JETSON-RESIDENT-VLM-CUDA-OOM-001` / `P05-JETSON-RESIDENT-VLM-REQUEST-001` | `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已证明 standalone resident VLM 可通过；但 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 中两次真实 resident VLM 请求仍分别报 `RemoteDisconnected` 与 `timeout` | 保持 P6/P7/P8 的 CPU-first VLM 参数：`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、更小 ctx/token budget；当前源码已额外支持 `VLM_DEVICE` 显式透传，可用 `VLM_DEVICE=none` 固定 llama.cpp multimodal server 的 device 路径，并把下一轮排查聚焦到 multimodal request path，而不再重复证明 standalone worker 是否能启动 |
| `P05-JETSON-RESIDENT-DETECTOR-CUDA-INIT-001` | 历史 `resident_concurrency_smoke_v3/v4/v6` 曾在 detector 写出首个 JSONL 之前出现 TensorRT/CUDA 初始化失败；但 `resident_concurrency_smoke_v8` 已在 `DETECTOR_START_ORDER=after_workers` + start retry 下进入有效 10 分钟窗口 | 保留 `DETECTOR_START_ORDER=after_workers`、`DETECTOR_START_RETRIES=2`、`DETECTOR_RESTART_DELAY_SEC=8` 作为 Jetson 并发默认基线，不再把 detector 冷启动失败作为当前第一阻塞点 |

### 本轮已落地的代码策略

| 优先级 | 策略 | 已落地位置 | 目的 |
|---|---|---|---|
| P1 | detector 冷启动失败自动重试 | `run_alarm_service.py` + `detector_service.py` 新增 `--detector-start-retries`、`--detector-restart-delay-sec` | 避免 Jetson 在一次短暂 CUDA/TensorRT 初始化失败后直接判整轮 run 失败 |
| P1 | resident/once VLM 请求级重试 | `run_alarm_service.py` + `vlm_worker.py` 新增 `--vlm-request-retries`，`llama_cpp_multimodal_resident` 与 `llama_cpp_multimodal_once` 都会在请求失败后按预算重试 | 避免首个请求超时后整条 VLM worker 或 async lane 直接报废 |
| P1 | postrun async VLM 冷却 + retry backoff | `run_jetson_p7_route_b_dual_service_smoke.sh` 新增 `ASYNC_POSTRUN_COOLDOWN_SEC`，`run_async_vlm_enrichment.py` / `vlm_worker.py` 新增 `--vlm-retry-backoff-sec` | 针对 `20260716_jetson_8gb_alarm_service_route_b_target_v1` 暴露出的“detector 刚退出后首个 async once 请求触发 `NvMap error 12` / `CUBLAS_STATUS_NOT_INITIALIZED`，而后续事件又能 pass”现象，给 Jetson target 一个显式资源释放和重试退避窗口 |
| P1 | async once 首请求预热 | `run_async_vlm_enrichment.py` / `vlm_worker.py` 新增 `--vlm-once-prewarm-request`、`--vlm-once-prewarm-max-tokens`；`run_jetson_p9_route_b_postrun_target.sh` 默认开启 | 针对 `20260716_jetson_8gb_alarm_service_route_b_target_v2` 暴露出的“30 秒 cooldown + 30 秒 backoff 后，首个真实 VLM 请求仍死在 CUDA 初始化，而第 2 个请求继续 pass”现象，用一个不计入正式结果的预热请求吸收首请求抖动；该策略已在 `20260717_jetson_8gb_alarm_service_route_b_target_v3` 验证有效 |
| P2 | Route B async once 默认重试 1 次 | `run_jetson_p7_route_b_dual_service_smoke.sh` 默认 `VLM_REQUEST_RETRIES=1` | 让 Jetson B 方案默认贴近已经通过的 P6 VLM 基线，而不是首错即停 |
| P2 | P6 standalone VLM 收紧默认负载 | `run_jetson_p6_resident_vlm_smoke.sh` 默认改为 `VLM_CTX=1536`、`VLM_MAX_TOKENS=96`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`、`VLM_IMAGE_MIN/MAX_TOKENS=512`、`VLM_REQUEST_RETRIES=1` | 先把 Jetson resident VLM 从“startup 成功但首个请求 timeout”推进到真正 pass |
| P2 | P7/P8 并发窗口继续 CPU-first | `run_jetson_p7_resident_service_smoke.sh`、`run_jetson_p8_resident_service_required.sh` 继续固定 `TEXT_NGL=0`、`TEXT_NO_KV_OFFLOAD=1`、`TEXT_DEVICE=none`、`VLM_NGL=0`、`VLM_NO_KV_OFFLOAD=1`、`VLM_NO_MMPROJ_OFFLOAD=1`，并支持通过 `VLM_DEVICE=none` 显式固定 VLM device | 先把 CUDA 容量优先让给 resident VLM，同时把 llama.cpp multimodal 的设备选择从 `auto` 收口到可控实验变量 |
| P3 | 收紧 P7/P8 VLM 输出预算 | 默认 `VLM_CTX` 由 `2048` 调到 `1536`，`VLM_MAX_TOKENS` 由 `192` 调到 `128`，`VLM_IMAGE_MIN/MAX_TOKENS` 由 `768` 调到 `512` | 降低首个 VLM 请求的预填充与 decode 压力 |
| P3 | 增加 detector 重启余量 | P7/P8 默认 `DETECTOR_START_RETRIES=2`、`DETECTOR_RESTART_DELAY_SEC=8` | 给 Jetson TensorRT/CUDA 初始化失败留一次以上自恢复机会 |
| P3 | frame-cache 产物收紧与清理 | P7/P8 默认 `FRAME_CACHE_CAPACITY=1536`，并把 frame-cache 清理改成 EXIT 路径 | 避免 Jetson 并发 smoke 失败后遗留大量 JPEG |

### 2026-07-14 `VLM_DEVICE=none` 对照实验结论

`VLM_DEVICE` 现在仍保留在 Jetson wrapper 中，但它已经不是“建议默认值”，而是“诊断开关”。

本轮已完成两组显式对照：

| run_id | 实验目的 | 结果 |
|---|---|---|
| `20260714_jetson_8gb_alarm_service_resident_vlm_device_none_smoke_v1` | 验证 standalone resident VLM 在 `VLM_DEVICE=none` 下是否更稳 | 失败；`vlm_rows=3`、`vlm_bad_rows=3`，前两条真实请求均 timeout，第三条因预算用尽未执行 |
| `20260714_jetson_8gb_alarm_service_resident_concurrency_vlm_device_none_v1` | 验证 Jetson P7 并发窗口里 `VLM_DEVICE=none` 是否能修复真实 VLM 请求 | 失败；`vlm_call_count=2`、`vlm_pass_rows=0`，两次真实请求都 timeout，且 `detection_fps=21.425603`，明显低于 `v8` |

因此当前结论已经明确：

- `VLM_DEVICE=none` 没有解决 Jetson resident multimodal request path。
- 它把失败模式从 `RemoteDisconnected + timeout` 收敛成了更稳定的 `timeout`，便于诊断，但不构成通过。
- Jetson 当前已验证真正有效的收口组合是 `ASYNC_POSTRUN_COOLDOWN_SEC=30` + `VLM_RETRY_BACKOFF_SEC=30` + `VLM_ONCE_PREWARM_REQUEST=1` + `VLM_ONCE_PREWARM_MAX_TOKENS=8`；`20260717_jetson_8gb_alarm_service_route_b_target_v3` 已把 postrun async VLM 推到严格 `2/2 pass`。
- 它还拖低了并发窗口吞吐，因此不能写进 Jetson P6/P7/P8 的默认参数。

从现在开始，Jetson 文档口径应固定为：

- `VLM_DEVICE=none` 仅用于 device-routing 对照实验。
- Jetson 默认主线不再建议继续用它作为收口方案。
- Jetson 真正待解决的问题是 resident multimodal request path，而不是单纯的 device 选择。

### 20260713 v8 后的新判断

`20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 已经通过，说明 standalone resident VLM 在 Jetson 上成立。  
随后 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v7` 首次把 Jetson P7 推进到有效 10 分钟窗口，但当时仍有明显 runtime backpressure：`drop_count=99`、`alarm_count=37/136`。  
在继续收紧默认值后，最新 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 已给出新的收口边界：

- `window_sec=630.325`
- `requested_window_sec=600.0`
- `window_requirement_met=true`
- `detection_fps=28.632848`
- `event_count=136`
- `alarm_count=136`
- `llm_call_count=2`
- `vlm_call_count=2`
- `event_queue_depth=91`
- `drop_count=0`
- `memory_mb=4866.0`
- `swap_used_mb=2304.0`
- `temperature_c=60.5`

同时，text resident 已在同一并发窗口内保持同一 `resident_server_pid=60424`、`resident_model_load_count=1`，两次真实请求都成功返回：

- request 1: `prefill_ms=52449.73`、`llm_total_ms=73175.216`、`decode_tokens_per_s=1.747388`
- request 2: `prefill_ms=30064.135`、`llm_total_ms=49351.53`、`decode_tokens_per_s=2.000796`

因此当前 Jetson 主阻塞点已经不再是：

- resident text startup；
- resident VLM startup OOM；
- detector 冷启动失败；
- queue backpressure。

当前真正剩余的问题已经收口为 resident multimodal request path：`v8` 中两次真实 VLM 请求分别失败为：

- 第 1 条：`RemoteDisconnected: Remote end closed connection without response`
- 第 2 条：`timeout: timed out`

这也是为什么 Jetson P7 现在不能再写成“尚未进入有效时间窗”或“先去证明 P6-VLM 能不能启动”。P6-VLM standalone 已过，P7 有效窗口也已过，当前只差并发窗口里的真实 VLM 请求通过判定。

### 现在必须按这个顺序收口

1. 以 `20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4` 作为 Jetson standalone resident VLM 基线。  
   只有在板端环境被重置、模型路径变化或 llama.cpp runtime 变化时，才需要先重跑 P6-VLM；否则不再把“P6-VLM 能不能启动”当成当前主问题。

2. 以 `20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8` 作为 Jetson P7 并发默认基线继续复测。  
   当前优先检查的是前两次真实 VLM 请求能否从 `fallback` 变成 `pass`；如果 detector 又重新在首个 JSONL 之前失败，才回到 TensorRT/CUDA 初始化问题；如果 `drop_count` 再次抬升，才回到 queue/backpressure 问题。

3. P7 通过后，再进入 Jetson P8 30 分钟 required。

### 当前基线命令

#### Jetson P6 resident VLM smoke

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260713_jetson_8gb_alarm_service_resident_vlm_smoke_v4
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export EVENTS_INPUT=benchmark/raw/05_alarm_system/${BOARD}/events/20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1_events.jsonl
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf
export VLM_CTX=1536
export VLM_MAX_TOKENS=96
export VLM_TIMEOUT_MS=180000
export VLM_NGL=0
export VLM_DEVICE=none
export VLM_NO_MMPROJ_OFFLOAD=1
export VLM_NO_KV_OFFLOAD=1
export VLM_IMAGE_MIN_TOKENS=512
export VLM_IMAGE_MAX_TOKENS=512
export VLM_REQUEST_RETRIES=1

bash projects/05_alarm_system/scripts/service/run_jetson_p6_resident_vlm_smoke.sh
```

#### Jetson P7 10 分钟并发 smoke

```bash
cd <BOARD_USER_HOME>/edge-inference-deploy-lab

export RUN_ID=20260713_jetson_8gb_alarm_service_resident_concurrency_smoke_v8
export BOARD=jetson_8gb
export ENV_BASELINE_ID=20260609_jetson_8gb_env_baseline
export DURATION_SEC=600
export TEXT_MAX_CALLS=2
export VLM_MAX_CALLS=2
export LLAMA_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-cli
export LLAMA_SERVER_BIN=<BOARD_USER_HOME>/tools/llama_cpp_cuda/llama.cpp/build-cuda/bin/llama-server
export QWEN3_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-1.7B-GGUF/qwen3-1.7b-q4_k_m.gguf
export QWEN3_VL_GGUF=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-q4_k_m.gguf
export QWEN3_VL_MMPROJ=<BOARD_USER_HOME>/edge-inference-deploy-lab/models/llm_vlm/Qwen3-VL-2B-Instruct-GGUF/qwen3-vl-2b-instruct-mmproj-f16.gguf
export TEXT_NGL=0
export TEXT_NO_KV_OFFLOAD=1
export TEXT_DEVICE=none
export TEXT_MAX_TOKENS=64
export TEXT_TIMEOUT_MS=180000
export QWEN_NO_THINK=1
export VLM_CTX=1536
export VLM_MAX_TOKENS=64
export VLM_TIMEOUT_MS=210000
export VLM_NGL=0
export VLM_DEVICE=none
export VLM_NO_MMPROJ_OFFLOAD=1
export VLM_NO_KV_OFFLOAD=1
export VLM_IMAGE_MIN_TOKENS=512
export VLM_IMAGE_MAX_TOKENS=512
export VLM_REQUEST_RETRIES=1
export DETECTOR_START_RETRIES=2
export DETECTOR_RESTART_DELAY_SEC=8
export DETECTOR_START_ORDER=after_workers
export SERVICE_QUEUE_CAPACITY=192
export FRAME_CACHE_CAPACITY=1536

bash projects/05_alarm_system/scripts/service/run_jetson_p7_resident_service_smoke.sh
```

### 通过标准

| 阶段 | 通过标准 |
|---|---|
| P6-VLM | `vlm_bad_rows=0`，同一 `resident_server_pid`，`resident_model_load_count=1`，请求序号单调递增 |
| P7 | `window_requirement_met=true`，detector 成功写出 `resident_detector.jsonl`，`llm_call_count=2`，`vlm_call_count=2`，`drop_count=0`，且真实结果中 `llm_pass_rows=2`、`vlm_pass_rows=2`，text/VLM 均保持同一 `resident_server_pid` 与 `resident_model_load_count=1` |
| P8 | 在 P7 标准基础上，30 分钟窗口内 `restart_count`、`error_count`、`drop_count` 仍可接受且可解释 |

