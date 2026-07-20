# Project 05 Specification Compliance Matrix

本矩阵以当前正式验收状态 `dual_board_target_pass_publishable_text_guard_pass` 为准。它区分“正式主线已验收”“按项目四决策禁用”“非阻塞诊断/后续可靠性增强”，不把历史失败或可选实验混入主线完成度。

| 规范 | 正式要求摘要 | 已采集证据 | 结论 |
|---|---|---|---|
| 05A Jetson 告警解释系统 | resident detector，高频检测不被低频解释阻塞；文本/VLM 只能低频；最终告警必须受事实约束 | `20260717_jetson_8gb_alarm_service_route_b_target_v3`；`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3` | pass，正式 Route B 为 detector + resident text + postrun async VLM；文本发布守卫 `3/3` 替换通过 |
| 05B RK3588 告警解释系统 | RKNN detector + RKLLM text/VLM 常驻低频消费，有界队列与稳定窗口 | `20260717_p05_dual_board_target_v1_rk3588` | pass，`7203.72 s`、`30.042395 FPS`、LLM/VLM 各 2 次、drop 0 |
| 05D 事件与 ROI | event package 有规则、检测事实与 ROI/keyframe 可追溯 | 双板 P9 event schema；Jetson postrun VLM enrichment；RK3588 frame-cache/ROI resident 路线 | pass，视觉资产仅按预算生成；不保存整窗 JPG |
| 05E Alarm JSON | 结构化 Alarm JSON、fallback、证据路径和 schema 校验 | 双板 P9 的 alarm schema；Jetson text guard v3 `3/3` Alarm JSON schema pass | pass，事实冲突有固定字段并保留 raw 审计 |
| 05F 稳定性监控 | required/target 持续窗口、队列、drop、资源监控 | Jetson P9 `7217.22 s`；RK3588 P9 `7203.72 s`；双板 overlap `7194.72 s` | pass，双板 target 门槛 `>=6900 s` 满足 |
| 05G Benchmark | 指标表、raw/processed schema、状态边界和可复核性 | `alarm_system_benchmark.md`、双板 summary、final manifest | pass，缺失的 e2e p95/功耗字段明确标为未采集，不伪造数值 |
| 05H 业务语义与规则 | `person_presence`、`vehicle_presence`、`multi_object_scene` 与 detector 事实一致 | 双板 P9 event/alarm records；Jetson fact guard v3 | pass，原始 LLM 无权扩展行为、身份或装备事实 |
| 05I Jetson 执行流程 | accepted Route B、P4/P6/P7/P8/P9、诊断分支区分 | Jetson P9、P6 text guard v3、双板 Jetson 槽位 | pass，same-window resident VLM 仅诊断，不阻塞主线 |
| 05J RK3588 执行流程 | Project5 local detector、resident text/VLM、P7/P8/P9 | RK3588 P7/P8/P9 与双板 RK3588 槽位 | pass |
| 05K 常驻服务与并发 | 本地 service、持续 detector、队列、worker 常驻复用、AlarmSink | Jetson accepted Route B；RK3588 同窗三常驻；P9 group summary | pass，板卡拓扑差异按规范分别验收 |
| 05L 独立代码边界 | 服务运行时不直接耦合项目三/四脚本 | `project5_code_boundary_check.md`：`independent_runtime_pass`；Project5 local runner/service 板端 run | pass，项目三/四仅作为 artifact/准入证据引用 |
| 05M 实施路线图 | 分阶段收口、优先级与目标路线明确 | P4--P9 证据、P6 text guard v3、最终报告 | pass，路线图已冻结为正式拓扑 |
| 05N 双板联调 | 同组 RUN、启动偏差、重叠时长、两板门槛 | `20260717_p05_dual_board_target_v1_dual_board_summary.json` | pass，start skew `22.5 s`、overlap `7194.72 s` |

## 非阻塞项

| 项目 | 分类 | 处理方式 |
|---|---|---|
| Jetson same-window resident VLM request path | 诊断分支 | 不替代 Route B；后续仅作为性能/兼容性研究。 |
| SmolVLM2 多帧视频理解 | 项目四禁用 | `D_not_used`，不作为项目五能力。 |
| 原始 Jetson Qwen3 文本直接发布 | 安全禁止项 | 必须经 `fact_guard.py`；原文仅供审计。 |
| 摄像头断流故障注入 | 后续可靠性增强 | 可独立立项采证，不影响本轮 target 验收结论。 |
