# video_understanding_benchmark

当前状态：`jetson_video_disabled_policy_verified_rk3588_required_interface_and_camera_verified`。

本报告记录项目五短视频片段理解指标。当前 Jetson 和 RK3588 的 SmolVLM2 多帧视频理解均不进入项目五主线，因此项目五默认不运行视频理解模型；`video_summary` 必须通过检测结果、关键帧/ROI 摘要和文本 LLM 规则化替代。

## 准入约束

| board | model | project4 decision | selected evidence | project5 decision |
|---|---|---|---|---|
| Jetson 8GB | SmolVLM2-500M-Video-Instruct | `D_not_used` | Transformers CUDA route 被 CPU-only PyTorch 阻塞；GGUF 多帧触发 context/media slot 不足 | 禁用，不进入项目五在线/低频链路 |
| RK3588 8GB | SmolVLM2-500M-Video-Instruct | `D_not_used` | 项目四仅保留诊断/失败证据，不能支撑项目五视频主线 | 禁用，不进入项目五在线/低频链路 |

## 指标表

| board | model | project4 decision | clip sec | sampled frames | decode ms | preprocess ms | first token ms | tokens/s | total ms | memory MB | swap MB | status | raw result |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Jetson 8GB | SmolVLM2 | `D_not_used` | 0 | 0 |  |  |  |  |  |  |  | `disabled_by_project4_decision_verified_in_required30min` | `benchmark/raw/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_alarm_system_benchmark.jsonl` |
| RK3588 8GB | SmolVLM2 | `D_not_used` | 0 | 0 |  |  |  |  |  |  |  | `disabled_by_project4_decision_verified_in_required_interface` | `benchmark/raw/05_alarm_system/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_alarm_system_benchmark.jsonl` |

## 双板替代视频摘要策略

| input | processing | output field | benchmark metric | status |
|---|---|---|---|---|
| event package detections | 聚合类别、置信度、持续帧、队列和时间戳 | `video_summary` | event_trigger/roi/video_clip latency | Jetson required30min 和 RK3588 interface smoke 已通过 event/alarm schema；summary 仍以 detector facts 为边界 |
| keyframe/ROI | 可选 Qwen3-VL 低频解释 | `vlm_summary` and derived `video_summary` | `vlm_total_ms`, timeout rate | Jetson/RK3588 本轮均为 VLM route stub only，不声明真实 ROI/VLM |
| short clip path | 只保留证据路径，不送入 SmolVLM2 | `video_clip_path` | clip generation latency | 双板本轮未生成真实短片段资产，视频模型保持禁用 |

## Jetson Required 30min 视频降级验证

| run_id | events | alarms | video model | VLM route | fallback evidence | status |
|---|---:|---:|---|---|---|---|
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | 397 | 397 | disabled by Project4 decision | 3 route stub rows | `fallback_count=397`, Alarm JSON schema pass | `video_disabled_policy_verified` |

本 run 完成的是“视频理解禁用后的结构化降级路径验证”，不是短视频模型理解 benchmark。397 条 Alarm JSON 证明系统能在视频模型禁用时保留检测事实、文本解释、VLM/video fallback 状态和 schema 合格输出；但没有证明短片段抽取、真实视频模型理解或真实 ROI 图文复核。

## RK3588 Interface Smoke 视频降级验证

| run_id | events | alarms | video model | VLM route | fallback evidence | status |
|---|---:|---:|---|---|---|---|
| `20260708_rk3588_8gb_alarm_system_smoke_v1` | 75 | 75 | disabled by Project4 decision | 3 route stub rows | `fallback_count=75`, Alarm JSON schema pass | `video_disabled_policy_verified_in_interface_smoke` |
| `20260708_rk3588_8gb_alarm_system_realtime30min_required_v1` | 200 | 200 | disabled by Project4 decision | 3 route stub rows | `fallback_count=200`, Alarm JSON schema pass | `video_disabled_policy_verified_in_required_interface` |
| `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | 2 | 2 | disabled by Project4 decision | 2 route stub rows | Alarm JSON rows=2 schema pass; per-event raw rows=2 schema pass | `video_disabled_policy_verified_in_camera_alarm_chain_smoke` |

required run 证明 RK3588 在视频模型禁用时可以生成 schema-safe Alarm JSON、per-event raw 和 required time-window raw；Astra S camera smoke 证明真实摄像头输入下也能走同一 video disabled / VLM route stub 降级路径。但这些 run 均不证明 SmolVLM2 视频理解或真实 Qwen3-VL ROI 复核。

## 输出质量

| event_id | expected behavior | summary | pass/fail | issue_id |
|---|---|---|---|---|
| pending | `video_summary` 明确标注来自检测/抽帧摘要，不声称多帧模型理解 |  |  |  |

## MLPerf-style Summary: Jetson Video Understanding

| field | value |
|---|---|
| Task | short-clip video understanding under alarm system integration |
| Board | Jetson 8GB and RK3588 8GB |
| Video model | SmolVLM2 disabled |
| Project4 level | `D_not_used` on both Project 05 mainline boards |
| Scenario | no multiframe video model; detector/keyframe/ROI summary fallback |
| Quality target | video fallback does not fabricate facts and does not overwrite detections |
| Performance result | no video model benchmark; Jetson required30min verified detector/event/alarm fallback path |
| Resource result | no video model resource usage |
| Raw result | no project5 video model raw; Jetson fallback evidence in `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` per-event/stability raw; RK3588 fallback evidence in required interface and Astra S camera alarm-chain smoke |
| Alarm JSON requirement | `fallback_status.video=disabled_by_project4_decision`; `video_summary` may be null or detector-derived |
| Known limitations | 不能把当前 Jetson/RK3588 写成 SmolVLM2 视频理解平台；Astra S camera run 也只是 detector/event/RKLLM/Alarm JSON 链路，不是视频模型理解 |
