# yolo11n_realtime_benchmark

当前状态：`jetson_required30min_detector_pass_project5_chain_pass_rk3588_required_detector_pass_astra_camera_detector_pass`。

本报告记录项目五中 YOLO11n 高频检测链路的指标。项目五不重新证明 YOLO 单模型能力，但必须证明系统整合后检测线程不被 LLM/VLM 阻塞。

## 继承输入

| 来源 | 用途 | Jetson 结论 |
|---|---|---|
| `projects/01_vision_deploy/reports/benchmark.md` | 单模型/单图检测基线 | 模型和前后处理口径来源 |
| `projects/03_video_pipeline/reports/runtime_benchmark.md` | C++ pipeline 检测基线 | TensorRT INT8 `runtime600` 已形成主线 |
| `projects/03_video_pipeline/reports/stability_report.md` | 检测链路稳定性基线 | 30 分钟和 2 小时 no-output 基线已验证 |

## Jetson 继承检测基线

| metric group | run_id | input source | backend | precision | FPS | p50 ms | p90 ms | p95 ms | p99 ms | queue max | drop count/rate | memory peak MB | temp max C | status |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| runtime600 selected | `20260617_jetson_8gb_yolo11n_tensorrt_int8_runtime600_playlist20_noout` | `video_set_runtime_v1` | TensorRT-GPU | INT8 PTQ | 30.0872 | not_in_report | not_in_report | 49.1965 | 52.2379 | 7 | `116 / 0.00643` | see project3 raw | see project3 raw | `selected_default_runtime_baseline` |
| multithread explicit comparison | `20260622_jetson_8gb_yolo11n_tensorrt_int8_multithread_pipeline` | `video_set_runtime_v1` | TensorRT-GPU | INT8 PTQ | 30.1302 | 60.1854 | 62.0441 | 63.7580 | 66.1065 | 5 | `0 / 0.0` | 3484.0 | 59.5 | `runtime_pass_all_postchecks_pass` |
| stability short | `20260617_jetson_8gb_yolo11n_tensorrt_stability_short_playlist80_noout` | `video_set_stability_v1` | TensorRT-GPU | INT8 PTQ | 30.0395 | not_in_report | not_in_report | 71.7296 | 74.4355 | 8 | `112 / 0.00207` | 2226.0 | 60.5 | `pass_noout_baseline` |
| stability acceptance | `20260617_jetson_8gb_yolo11n_tensorrt_stability_acceptance_playlist80_noout` | `video_set_stability_v1` | TensorRT-GPU | INT8 PTQ | 30.0573 | not_in_report | not_in_report | 52.0953 | 53.9539 | 7 | `110 / 0.00051` | 3920.0 | 60.0 | `pass_noout_baseline` |

## 项目五系统整合后指标

| board | model combo | detector backend | input source | project3 baseline FPS | system FPS | FPS delta | project3 p95 ms | system p95 ms | p99 ms | queue max | drop count | LLM/VLM enabled | status | raw result |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Jetson 8GB | `jetson_8gb_alarm_combo_v2_project4_selected` | TensorRT INT8 | `video_set_runtime_v1` | 30.0872 | 30.0722 | -0.0150 | 49.1965 | 61.794 | 63.859 | 7 | 0 | text=Qwen3 low-frequency checked rows=10; VLM route stub; video=disabled | `required30min_pass_with_caveat` | `benchmark/raw/03_video_pipeline/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1.jsonl` |
| RK3588 8GB | `rk3588_8gb_alarm_combo_v1` | RKNN INT8 | `video_set_runtime_v1` | project3 selected detector baseline | 30.0722 | pending delta | project3 selected detector baseline | 119.78855 | 124.69598 | 7 | 0 | text=template rows=10; VLM=route stub rows=3; video=disabled | `required_detector_pass_interface_schema_pass` | `benchmark/raw/03_video_pipeline/rk3588_8gb/20260708_rk3588_8gb_alarm_system_realtime30min_required_v1_project3_detector.jsonl` |
| RK3588 8GB | `rk3588_8gb_alarm_combo_v1` | RKNN INT8 | `astra_s_openni_001` OpenNI camera | not applicable | 29.6033 | camera source | not applicable | 121.51645 | 125.77600 | 1 | 0 | detector adapter generated 17762 Project5 rows; event package rows=2 | `camera_detector_event_package_pass` | `benchmark/raw/03_video_pipeline/rk3588_8gb/20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1_project3_detector.jsonl` |

## 项目五必填检测指标

| category | required metric | Jetson inherited value | project5 value | evidence path |
|---|---|---|---|---|
| throughput | FPS avg/min/max | avg `30.0872` from project3 runtime600 | required run avg `30.0722` | `benchmark/processed/03_video_pipeline/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_summary.csv` |
| latency | p50/p90/p95/p99 end-to-end detector latency | p95 `49.1965 ms`, p99 `52.2379 ms` from project3 runtime600 | p50 `58.633 ms`, p90 `60.198 ms`, p95 `61.794 ms`, p99 `63.859 ms` | project3 required run summary |
| stage latency | capture/preprocess/infer/postprocess/output p95/p99 | available in project3 detailed tables | captured in project3 raw/summary | project3 required run raw |
| queue | queue max, wait ms, drop count, drop reason | queue max `7`, drop `116` in runtime600 noout | queue max `7`, drop rate `0.0` | project3 required run summary + Project5 stability raw |
| trace | frame gaps, out-of-order, missing timestamps | project3 selected run trace checked | schema pass, trace pass, frame_id_gaps=0 | `benchmark/processed/03_video_pipeline/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_trace_check.md` |
| resource | memory, swap, temp, CPU/GPU util, power mode | memory/temp inherited where available; power not recorded | Project5 monitor memory `3001.0 MB`, swap `195.0 MB`, temp `68.5 C`; power unavailable | `logs/monitor/05_alarm_system/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1_e2e_tegrastats.log` |
| isolation | detector FPS delta with LLM/VLM enabled | not applicable in project3 | detector 30min pass + Project5 post-detector chain pass; not full resident concurrency claim | Project5 required run raw and reports |

## MLPerf-style Summary: Jetson Detector Baseline

| field | value |
|---|---|
| Task | YOLO11n realtime detector under alarm system integration |
| Board | Jetson 8GB |
| Detector | YOLO11n TensorRT INT8 PTQ |
| Backend/runtime | TensorRT-GPU via project3 C++ pipeline |
| Backend artifact | `models/yolo11n/tensorrt/yolo11n_640_jetson_trt_int8_ptq_calib500_minmax_b8.engine` |
| Backend artifact SHA256 | `1e966f10db6742476414294f931948b4732a4a44c07479022eca34869ab5ca9d` |
| Input source | project3 selected baseline `video_set_runtime_v1`; Project5 required run used same source raw |
| Scenario | high-frequency detector path with asynchronous alarm-event workers |
| Quality target | detector trace remains valid; LLM/VLM does not block detector |
| Performance result | required run detector: `30.0722 FPS`, p95 `61.794 ms`, p99 `63.859 ms`, drop rate `0.0` |
| Resource result | Project5 monitor: memory `3001.0 MB`, swap `195.0 MB`, temp `68.5 C`; power unavailable |
| Stability result | Project3 detector 1800s pass; Project5 required 30min post-detector chain pass |
| Raw result | `benchmark/raw/03_video_pipeline/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1.jsonl` |
| Logs | `logs/runtime/03_video_pipeline/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1.log`; Project5 logs under `logs/runtime/05_alarm_system/jetson_8gb/` |
| Known limitations | 本 run 证明 detector 30min 和 Project5 后处理链路通过；不声明 LLM/VLM 与 detector 的完整常驻并发服务 |
