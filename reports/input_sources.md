# 项目五输入源清单

当前输入源状态：`jetson_video_required30min_pass_jetson_project5_resident_detector_smoke_pass_jetson_resident_text_worker_smoke_pass_camera_detector_smoke_no_events_rk3588_astra_camera_alarm_chain_smoke_pass_rk3588_project5_resident_detector_smoke_pass_rk3588_project5_resident_required_pass`。

本文件定义项目五固定视频、摄像头和 RTSP 输入源的最低字段。Jetson required 30min 当前使用项目三已验证的 `video_set_runtime_v1` detector raw 作为项目五输入；摄像头源应优先继承项目三 `video_fixed_v1.yaml` 中已经验证或记录失败的板端输入源，再执行项目五 detector -> event -> alarm 链路。

项目四不包含摄像头实时 pipeline，它提供的是 LLM/VLM 模型准入和视频模型禁用结论；摄像头采集、V4L2/OpenNI/RTSP 接入代码主要继承项目三。

Manifest：

```text
projects/05_alarm_system/configs/inputs/video_sources.yaml
```

## 输入源表

| input_source_id | source_type | uri | camera_id | fps | resolution | duration | sha256 | availability | notes |
|---|---|---|---|---:|---|---:|---|---|---|
| video_set_runtime_v1 | video_playlist via Project3 detector raw | `benchmark/raw/03_video_pipeline/jetson_8gb/20260708_jetson_8gb_alarm_system_realtime30min_required_v1.jsonl` | project3_runtime_video_set | 30.0722 measured | see Project3 source manifest | 1800.0 | detector raw governed by Project3 artifact | verified_for_jetson_required30min | Project5 使用该 raw 生成 397 events / 397 alarms；不是 USB/RTSP 摄像头直连 |
| video_set_runtime_v1_project5_resident_jetson | video_playlist via Project5 local detector service | `data/videos/runtime_playlist_v1.txt` | project5_jetson_resident_detector_service | 29.458286 measured | normalized by Project5 local TensorRT detector | 612.629 | null | verified_for_jetson_resident_detector_smoke | `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1`：Project5 local detector raw、event/alarm 链路在线生成，template/stub worker 不触发真实解释模型 |
| video_set_runtime_v1_project5_resident_rk3588 | video_playlist via Project5 local detector service | `data/videos/runtime_playlist_v1.txt` | project5_rk3588_resident_detector_service | 30.035697 measured | normalized by Project5 local RKNN detector | 600.885 | null | verified_for_rk3588_resident_detector_smoke | `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2`：Project5 local detector raw 18048 行，event/alarm 各 75 行，drop=0 |
| video_set_runtime_v1_project5_resident_rk3588_required | video_playlist via Project5 local detector service | `data/videos/runtime_playlist_v1.txt` | project5_rk3588_resident_required_service | 30.010783 measured | normalized by Project5 local RKNN detector | 1803.685 | null | verified_for_rk3588_resident_required | `20260713_rk3588_8gb_alarm_service_resident_required_v2`：Project5 local resident detector + resident text/VLM 同窗 30 分钟，event/alarm 各 200 行，drop=0；当前 wrapper 默认只保留少量真实 VLM 资产并在退出时清理 frame cache |
| imx219_csi_001 | mipi_camera | `/dev/video0` | imx219_csi_001 | 47.3 measured in smoke | 1280x720 | 120.0 smoke | null | camera_detector_smoke_pass_no_alarm_event | Jetson CSI IMX219；Project3 detector 5676 frames schema/trace pass，Project5 adapter 5676 rows，event trigger 0 rows because no person/vehicle/multi_object trigger |
| imx219_csi_argus_001 | mipi_camera_argus | `jetson_argus_default` | imx219_csi_argus_001 | 30.0 inherited | 1280x720 | live_stream | null | inherited_probe_failed_current_board | 项目三 Argus probe 当前失败，不能作为 Project5 pass 路径 |
| fixed_alarm_video_001 | video_file | `data/videos/05_alarm_system/fixed_alarm_video_001.mp4` | fixed_video_001 |  |  |  |  | not_verified | 固定视频 benchmark 占位 |
| usb_camera_001 | usb_camera | `/dev/video0` | usb_camera_001 |  |  |  | null | candidate_requires_board_probe | 通用 UVC 占位；Jetson 当前优先使用 `imx219_csi_001` |
| rtsp_camera_001 | rtsp | `rtsp://<host>/<stream>` | rtsp_camera_001 |  |  |  | null | not_verified | RTSP 演示占位 |
| astra_s_openni_001 | openni_camera | `2bc5/0402` | astra_s_openni_001 | 29.6033 measured in smoke | 640x480 | 600.0 smoke | null | rk3588_camera_alarm_chain_smoke_pass | RK3588 Astra S；Project3 detector 17762 frames schema/trace pass，Project5 adapter 17762 rows，event trigger 2 rows，真实 RKLLM 2 rows，Alarm JSON 2 rows |

## Jetson Required 30min 输入源结论

| run_id | source | detector frames | duration sec | schema/trace | Project5 use | status |
|---|---|---:|---:|---|---|---|
| `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` | Project3 `video_set_runtime_v1` detector raw | 54130 | 1800.0 | pass / pass | 397 event packages, 397 Alarm JSON rows | `verified_for_video_file_playlist_path` |

该结论只覆盖固定视频/视频列表经 Project3 detector 产生 raw 后进入 Project5 的路径。Jetson CSI 摄像头源 `imx219_csi_001` 已有项目三输入源和采集代码依据，但尚未完成项目五告警链路 run；RTSP 摄像头、摄像头断流恢复和直接摄像头到 Project5 的实时输入链路也尚未完成。

## Jetson Resident Detector Smoke 输入源结论

| run_id | source | detector rows | duration sec | fps | Project5 mode | event rows | alarm rows | status |
|---|---|---:|---:|---:|---|---:|---:|---|
| `20260713_jetson_8gb_alarm_service_resident_detector_smoke_v1` | `video_set_runtime_v1`, Project5 local TensorRT detector service, `resident_process` | 18048 | 612.629 | 29.458286 | template/stub workers, online AlarmSink | 136 | 136 | `resident_detector_smoke_pass_with_template_stub_workers` |

该 run 证明 Jetson 固定视频列表已经不仅能走“Project3 detector raw -> Project5 replay”路径，也能走“Project5 本地 detector service -> online event/alarm”路径。随后 `20260713_jetson_8gb_alarm_service_resident_text_smoke_v1` 又通过 `--events-input` 复用了这条已验证事件流，拿到 `resident_text_worker_smoke_pass`；但那条 run 证明的是 resident 文本 worker 复用，不新增新的 source media 结论。Jetson resident VLM 仍未接入正式 resident 运行。

## Jetson Camera Smoke 输入源结论

| run_id | source | detector frames | duration sec | fps | Project3 schema/trace | Project5 adapter rows | event rows | status |
|---|---|---:|---:|---:|---|---:|---:|---|
| `20260708_jetson_8gb_alarm_system_camera_imx219_smoke_v1` | `imx219_csi_001`, V4L2 raw 1280x720 mode5 | 5676 | 120.0 | 47.3 | pass / pass | 5676 | 0 | `camera_detector_input_pass_no_alarm_event` |

该 camera smoke 证明 Jetson IMX219 摄像头可通过项目三 detector raw 接入项目五 adapter。`event rows=0` 是当前画面未满足 `person_presence`、`vehicle_presence`、`multi_object_scene` 触发条件，不按系统失败处理；它也不能替代视频端 `20260708_jetson_8gb_alarm_system_realtime30min_required_v1` 的 397 条告警链路 pass 证据。

## RK3588 Camera Smoke 输入源结论

| run_id | source | detector frames | duration sec | fps | Project3 schema/trace | Project5 adapter rows | event rows | alarm types | status |
|---|---|---:|---:|---:|---|---:|---:|---|---|
| `20260708_rk3588_8gb_alarm_system_camera_astra_smoke_v1` | `astra_s_openni_001`, OpenNI `2bc5/0402`, 640x480 | 17762 | 600.0 | 29.6033 | pass / pass | 17762 | 2 | `visual_detection/person_presence=2` | `camera_alarm_chain_smoke_pass_with_vlm_stub` |

该 camera smoke 证明 RK3588 Astra S OpenNI 摄像头可通过项目三 RKNN detector raw 接入项目五 adapter，并能生成 schema-safe event package、真实 RKLLM 文本解释、Alarm JSON 和 per-event benchmark raw。当前 VLM 仍为 route stub，且没有 Project5 time-window stability raw，因此不能写成真实 VLM 或稳定性通过。

## RK3588 Resident Detector Smoke 输入源结论

| run_id | source | detector rows | duration sec | fps | Project5 mode | event rows | alarm rows | monitor rows | status |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `20260710_rk3588_8gb_alarm_service_resident_detector_smoke_v2` | `video_set_runtime_v1`, Project5 local RKNN detector service, `resident_process` | 18048 | 600.885 | 30.035697 | template/stub workers, online AlarmSink | 75 | 75 | 556 | `resident_detector_smoke_pass_with_template_stub_workers` |

该 run 证明 RK3588 固定视频列表不仅能走“Project3 detector raw -> Project5 replay”路径，也能走“Project5 本地 detector service -> online event/alarm”路径。当前输入源结论仍只覆盖 resident detector smoke，不覆盖 resident RKLLM/VLM、摄像头断流恢复或完整并发常驻服务。

## RK3588 Resident Required 输入源结论

| run_id | source | detector rows | duration sec | fps | Project5 mode | event rows | alarm rows | llm/vlm calls | queue depth | drop_count | status |
|---|---|---:|---:|---:|---|---:|---:|---|---:|---:|---|
| `20260713_rk3588_8gb_alarm_service_resident_required_v2` | `video_set_runtime_v1`, Project5 local RKNN detector service, `resident_process` | 54130 | 1803.685 | 30.010783 | resident text + resident VLM + online AlarmSink | 200 | 200 | `llm=2`, `vlm=2` | 24 | 0 | `resident_service_required_pass_with_resident_text_vlm_workers` |

该 run 证明 RK3588 固定视频列表已经完成 Project5 单板 30 分钟 resident required。需要注意的是，当前同步回来的老 run 目录仍可能包含较大的 `frame_cache` 和资产目录；后续 wrapper 默认只为真实 VLM 调用生成少量 keyframe/ROI，并在 run 结束后清理 detector-side `frame_cache_dir`，不再保留整窗口 JPEG 缓存。

## 可复用实现

| source | reusable code/config | Project5 use |
|---|---|---|
| Jetson CSI IMX219 | `projects/03_video_pipeline/src/video_pipeline_app.cpp` 中 V4L2 raw camera path；`projects/03_video_pipeline/configs/streams/video_fixed_v1.yaml` 的 `imx219_csi_001` | 先用项目三生成 camera detector raw，再复用项目五 detector adapter、event trigger、LLM、Alarm JSON |
| Jetson Argus | 同一项目三 app 的 GStreamer/OpenCV capture path；`imx219_csi_argus_001` | 当前 probe failed，只能作为待修复路线 |
| RTSP / USB | 项目三 OpenCV `VideoCapture` / GStreamer path | Project5 需要先完成 board probe 和项目三 raw，再进入告警链路 |
| Project4 video | `projects/04_llm_vlm_independent/reports/project5_integration_decision.md` | 只继承视频模型禁用和 LLM/VLM 准入结论，不继承摄像头 pipeline |

## 维护规则

- 固定视频一旦替换，必须更新 `video_sha256`、fps、分辨率、时长、编码格式和所有相关 run。
- 摄像头或 RTSP 输入必须记录可访问性检查时间、设备路径或 stream URL、失败原因和 fallback。
- `not_verified` 输入源不能作为正式 benchmark 结论依据，只能用于接口联调或待补证据状态。
