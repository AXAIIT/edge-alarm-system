# Project 05 Experiment Closeout

## 收口决定

项目五于 2026-07-18 正式收口，状态为：

`closed / dual_board_target_pass_publishable_text_guard_pass`

收口依据不是单一 smoke，而是以下完整证据链：

| 验收域 | 已完成证据 | 结果 |
|---|---|---|
| Jetson accepted Route B target | `20260717_p05_dual_board_target_v1_jetson` | `7217.22 s`、`30.000887 FPS`、events/alarms `1550/1550`、drop `0` |
| RK3588 resident target | `20260717_p05_dual_board_target_v1_rk3588` | `7203.72 s`、`30.042395 FPS`、events/alarms `765/765`、LLM/VLM `2/2`、drop `0` |
| 双板协同 | `20260717_p05_dual_board_target_v1_dual_board_summary.json` | start skew `22.5 s`、有效重叠 `7194.72 s`、`dual_board_target_ready` |
| Jetson 发布侧文本安全 | `20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` | 同一模型一次加载、3 次真实 no-think 请求、`3/3` 冲突替换、Alarm schema `3/3 pass` |
| 结构化产物 | 双板 P9 10 份 schema report + Jetson text guard 4 份 schema report | `14/14 pass` |
| 代码边界 | `project5_code_boundary_check.md` | `independent_runtime_pass` |

## 正式交付拓扑

| board | 交付拓扑 |
|---|---|
| Jetson 8GB | Project5 local resident TensorRT detector + resident Qwen3 text；VLM 在同一 `RUN_ID` 的 postrun async enrichment 执行；最终 Alarm JSON 必须经 `fact_guard.py`。 |
| RK3588 8GB | Project5 local resident RKNN detector + resident RKLLM text + resident Qwen3-VL worker；低频模型通过有界队列和 call budget 消费事件。 |

## 不属于未完成项的限制

| 项目 | 收口处理 |
|---|---|
| Jetson same-window resident VLM | 诊断路线，不是 accepted Route B 的交付要求。 |
| SmolVLM2 多帧视频模型 | 项目四决策为 `D_not_used`，不进入项目五验收范围。 |
| 原始 Jetson Qwen3 文本 | 可用于审计，不能直接发布；事实守卫是正式系统边界。 |
| 摄像头断流故障注入 | 后续可靠性增强，不影响本轮完整实验的验收。 |
| RDK X5 | 已按项目四准入失败结论移出项目五主线。 |

## 复验要求

交付或同步后必须执行：

```bash
python3 projects/05_alarm_system/scripts/benchmark/verify_final_acceptance_manifest.py
```

期望输出：

```text
acceptance_status=dual_board_target_pass_publishable_text_guard_pass
```

该命令会验证 25 份带 SHA-256 的证据，包括原始 JSONL 计数、14 份 schema report、双板 target 聚合、Jetson 发布侧文本守卫和独立代码边界。
