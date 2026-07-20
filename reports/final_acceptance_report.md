# Project 05 Final Acceptance Report

**结论：`dual_board_target_pass_publishable_text_guard_pass`。**

**实验状态：`closed`。** 收口时间为 2026-07-18；后续只允许受控回归或单独立项的可靠性增强，不得以历史诊断失败推翻本报告已冻结的 accepted topology。

本报告冻结截至 2026-07-18 的项目五正式验收边界。项目四模型准入仅作为继承输入；本报告的结论只由项目五 raw JSONL、schema check、runtime/monitor log 和双板聚合结果支持。

## 正式拓扑

| board | 高频实时链路 | 低频解释链路 | 正式边界 |
|---|---|---|---|
| Jetson 8GB | Project5 local resident TensorRT detector + resident Qwen3 text | 同一 `RUN_ID` 的 postrun async Qwen3-VL enrichment | 文本原文必须经过 `fact_guard.py`；旧 same-window resident VLM 仅诊断，不阻塞 Route B |
| RK3588 8GB | Project5 local resident RKNN detector | resident RKLLM text + resident RKLLM/RKNN VLM 同窗低频消费 | LLM/VLM 均以 call budget 低频执行，检测队列保持有界 |

## 双板 Target Benchmark

| 指标 | Jetson `20260717_p05_dual_board_target_v1_jetson` | RK3588 `20260717_p05_dual_board_target_v1_rk3588` | 验收 |
|---|---:|---:|---|
| sustained window | `7217.22 s` | `7203.72 s` | 两者均超过 `7200 s` |
| detector FPS | `30.000887` | `30.042395` | pass |
| event / alarm count | `1550 / 1550` | `765 / 765` | pass |
| drop count | `0` | `0` | pass |
| real LLM calls | `2` | `2` | pass |
| real VLM calls | postrun async `2/2 pass` | resident `2/2 pass` | pass |
| group start skew | `22.5 s` | - | pass |
| effective overlap | `7194.72 s` | - | threshold `>=6900 s`, pass |
| group aggregate status | `dual_board_target_ready` | `dual_board_target_ready` | pass |

组级证据：`benchmark/processed/05_alarm_system/20260717_p05_dual_board_target_v1_dual_board_summary.{md,json}`。

可复现性入口：`projects/05_alarm_system/scripts/benchmark/verify_final_acceptance_manifest.py` 会重新核对本报告引用的原始/processed 证据并生成包含 SHA-256 的 manifest；任何关键证据变更都会使校验失败或产生新的 hash。

该校验器已覆盖双板 P9 的 event/alarm/stability JSONL 计数、10 份 target schema report、Jetson P6 v3 的 4 份 schema report、发布侧冲突替换以及 `independent_runtime_pass` 代码边界检查。

规范逐项覆盖情况见 `projects/05_alarm_system/reports/spec_compliance_matrix.md`。

## Jetson Publishable Text Guard

| 指标 | `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` | 验收 |
|---|---:|---|
| resident server pid / model load | `1901315 / 1` | 单次加载、多请求复用，pass |
| real no-think requests | `3` | pass |
| request index | `1/2/3` | 单调递增，pass |
| raw LLM fact conflicts | `3/3` | 原文仅审计，不直接发布 |
| publishable detector-fact replacements | `3/3` | pass |
| Alarm JSON schema | `3/3 pass` | pass |
| request total ms | `39917.693 / 25531.073 / 32115.090` | 已记录，不作为实时检测 SLA |
| decode tok/s | `5.1217 / 5.2977 / 5.2216` | 已记录 |

发布约束：`json_fact_conflict=true`、`fact_conflict_detail`、`fallback_status.alarm_json=fact_conflict_detected` 必须同时写入最终 Alarm JSON；`llm_raw_output` 保留用于审计。

## Schema Evidence

| 证据组 | event | alarm | raw benchmark | stability |
|---|---|---|---|---|
| 双板 Jetson P9 | pass | pass | pass | pass |
| 双板 RK3588 P9 | pass | pass | pass | pass |
| Jetson text guard v3 | pass | pass | pass | pass |

## 非阻塞限制

| 项目 | 当前处理 |
|---|---|
| Jetson same-window resident VLM | 保留为诊断分支；正式方案使用 postrun async VLM enrichment。 |
| SmolVLM2 多帧视频理解 | 按项目四 `D_not_used` 禁用；只保留 detector/关键帧事实。 |
| 原始 Jetson Qwen3 文本 | 不视为可直接发布；必须经过 `fact_guard.py`。 |
| 摄像头断流故障注入 | 未纳入本轮 target 必过项；后续可靠性增强应单独采证，不能反向修改本报告的 target 结论。 |
