# 05D_事件触发与抽帧ROI规范

## 适用范围

本规范定义 YOLO 检测结果如何触发事件、抽帧、裁剪 ROI、截取短视频片段，并生成项目五统一 event package。

event package 是项目五的中心证据对象。后续 VLM、视频理解、LLM 告警解释、JSON 输出、benchmark 和问题库都必须引用同一个 `event_id`。

告警业务语义、候选事件和禁用告警类型以 `projects/05_alarm_system/specs/05H_告警业务语义与事件规则规范.md` 为准。正式 run 不允许把任意检测框直接写成业务告警；没有人工质量评估时只能写 `candidate` 或 `not_verified`。

## 执行原则

事件触发可以由 C++ pipeline、Python adapter 或服务端模块实现，但输出字段必须一致。不能只保存截图或临时图片；必须能从 event_id 反查源视频、frame_id、检测结果、ROI 坐标、关键帧、短视频片段、触发规则和后续模型输出。

## 路径口径

| 类型 | 路径 |
|---|---|
| 事件规则 | `projects/05_alarm_system/configs/event_rules/` |
| run 记录 | `projects/05_alarm_system/runs/<run_id>/run.md` |
| 项目报告 | `projects/05_alarm_system/reports/event_pipeline.md` |
| event package | `benchmark/raw/05_alarm_system/<board>/events/` |
| ROI / keyframe 索引 | `benchmark/raw/05_alarm_system/<board>/events/` |
| runtime 日志 | `logs/runtime/05_alarm_system/<board>/` |
| failure 日志 | `logs/failures/05_alarm_system/<board>/` |

图片和视频片段可以保存在 `data/images/`、`data/videos/` 或 run 指定的 artifact 目录中，但 event package 必须记录绝对或仓库相对路径。

## 前置条件

- YOLO 检测链路可运行，输出包含 frame_id、timestamp、class_id、confidence、bbox。
- 已定义事件规则和类别阈值。
- 已按 05H 明确定义 `alarm_domain` 和 `alarm_type`，并确认当前规则不使用 `generic_object_event`。
- 已定义 event_id 生成规则。
- 已准备固定视频或摄像头输入。
- 已准备 ROI 裁剪和视频片段截取工具。
- run 记录必须对齐 `projects/05_alarm_system/specs/00_run_record_template.md`。
- event package 必须符合 `benchmark/schemas/alarm_event_package_schema.json`。
- per-event raw 中的事件字段必须符合 `benchmark/schemas/alarm_system_raw_schema.json`。

## event_id 规则

推荐格式：

```text
<project>_<board>_<source_id>_<timestamp_ms>_<rule_id>_<seq>
```

示例：

```text
05_jetson_8gb_cam01_20260601T153012123_person_zoneA_00017
```

event_id 必须满足：

- 同一 run 内唯一。
- 能从 event_id 或 event package 找到 source_id、frame_id 和 timestamp。
- 不能因为重试 LLM/VLM 而改变。
- 同一个事件的 VLM、视频理解、LLM 和告警 JSON 必须使用同一个 event_id。

## 事件触发规则

事件规则至少支持：

| 规则项 | 说明 |
|---|---|
| class filter | 只对指定类别触发 |
| alarm domain | 规则对应的任务域；检测触发规则默认 `visual_detection` |
| alarm type | 规则对应的告警或解释语义 |
| confidence threshold | 检测置信度阈值 |
| zone / ROI region | 只对指定区域触发 |
| duration frames | 连续 N 帧满足才触发 |
| cooldown seconds | 同类事件冷却时间 |
| max pending events | 队列最大事件数 |
| priority | 事件优先级 |
| snapshot policy | 保存关键帧策略 |
| clip policy | 事件前后片段时长 |

示例配置路径：

```text
projects/05_alarm_system/configs/event_rules/jetson_rules.yaml
projects/05_alarm_system/configs/event_rules/rk3588_rules.yaml
```

正式 run 的 `class_filter` 不允许为空。空 `class_filter`、`generic_object_event` 或所有类别通用触发只能用于接口调试，报告状态必须写 `not_verified_interface_only`。

## event package 字段

每条事件至少包含：

```text
event_id
run_id
board
source_id
camera_id
frame_id
timestamp
trigger_rule_id
trigger_reason
alarm_domain
alarm_type
event_stage
detections
keyframe_path
roi_paths
roi_boxes
video_clip_path
pre_event_seconds
post_event_seconds
queue_depth_at_trigger
detector_latency_ms
event_trigger_latency_ms
roi_crop_latency_ms
video_clip_latency_ms
status
log_paths
```

`detections` 必须保留原始检测事实，后续 LLM/VLM 只能引用，不能覆盖。`event_stage` 第一阶段默认写 `candidate`；只有固定事件集和人工质量评估完成后，才允许写 `verified`。

如果 `keyframe_path`、`roi_paths` 或 `video_clip_path` 为 `null`，event package 可以作为接口或候选事件证据继续进入 schema 检查，但不能判定为完整 ROI/抽帧/短片段证据通过。正式报告必须把这类 run 写成 `not_verified_interface_smoke`、`not_verified_candidate_only` 或对应降级状态。

## 执行步骤

### 1. 建立 run 记录

新建：

```text
projects/05_alarm_system/runs/<date>_<board>_event_trigger_roi/run.md
```

记录输入源、检测结果路径、事件规则、ROI 策略、clip 策略和输出路径。

### 2. 读取检测结果

输入可以来自：

- 项目三实时 pipeline 输出。
- 项目五 detector adapter 输出。
- 固定检测 JSON 回放。

输入必须包含 frame_id 和 timestamp；缺失时不能进入正式 benchmark，只能做调试。

### 3. 应用事件规则

推荐命令：

```bash
python3 projects/05_alarm_system/scripts/run_demo/run_event_trigger.py \
  --detections benchmark/raw/05_alarm_system/<board>/<date>_<board>_detector_events.jsonl \
  --rules projects/05_alarm_system/configs/event_rules/<board>_rules.yaml \
  --output benchmark/raw/05_alarm_system/<board>/events/<date>_<board>_event_packages.jsonl \
  > logs/runtime/05_alarm_system/<board>/<date>_<board>_event_trigger.log 2>&1
```

### 4. 保存关键帧和 ROI

必须记录：

- 原始帧路径。
- ROI 坐标，使用原图坐标系。
- ROI 图片路径。
- 类别、置信度和对应 detection_id。
- 裁剪是否越界、是否 padding、是否 resize。

ROI 失败不能静默跳过，必须进入 event package 的 `status` 和 failure 日志。

当前 `run_event_trigger.py` 只负责把检测事实和 `roi_boxes` 写入 event package，不从 Project3 raw 反推出图片。若后续要执行真实 Qwen3-VL/RKLLM 多模态复核，必须先生成可读取的 `keyframe_path` 或 `roi_paths`。推荐做法是在 Project3 detector run 中设置 `SAVE_OUTPUT_VIDEO=1`，随后用保存的视频抽取事件帧和 ROI：

```bash
python3 projects/05_alarm_system/scripts/run_demo/extract_event_assets_from_video.py \
  --events benchmark/raw/05_alarm_system/<board>/events/<run_id>_events.jsonl \
  --video projects/03_video_pipeline/runs/<project3_run_id>/outputs/<project3_run_id>.mp4 \
  --asset-dir data/images/05_alarm_system/<board>/<run_id> \
  --output-events benchmark/raw/05_alarm_system/<board>/events/<run_id>_events_with_assets.jsonl \
  2>&1 | tee logs/runtime/05_alarm_system/<board>/<run_id>_extract_event_assets.log
```

抽取脚本按 `frame_id` 从保存视频定位帧，并按 event package 中的 `roi_boxes`/`detections.bbox` 裁剪 ROI。该路径只适用于 Project3 输出视频与 raw frame_id 一一对应的 run；如果摄像头 run 没有保存 output video，事后无法恢复当时的真实关键帧，必须重跑摄像头 detector 并开启 `SAVE_OUTPUT_VIDEO=1`。

真实 VLM 调用的最低门槛：

- `keyframe_path` 或至少一个 `roi_paths` 指向存在的图片。
- event package schema 通过，且 detections、bbox、class/confidence 未被抽帧脚本改写。
- VLM raw 中 `mode` 必须是实际模型后端，例如 `rkllm_multimodal`；`stub_not_model_execution` 只能算接口路由。
- 如果图片资产缺失，真实 VLM 脚本必须写 `blocked_no_image_asset` 或直接失败，不能静默改成成功。

### 5. 截取短视频片段

必须记录：

- 事件前后时长。
- 原始视频源。
- 片段帧率、分辨率、编码格式。
- 是否因缓存不足导致片段不完整。

视频理解模型是否使用该片段，由项目四准入和项目五板卡 spec 决定。

### 6. 队列与限流

事件队列必须记录：

```text
queue_depth
enqueue_ts
dequeue_ts
wait_ms
drop_policy
drop_reason
priority
```

推荐策略：

- 高频检测线程只负责写入事件队列。
- VLM/LLM 消费事件队列，不能阻塞检测线程。
- 队列满时优先丢弃低优先级或重复事件。
- 丢弃必须计数并写入 benchmark。

`drop_policy` 统一使用：`drop_low_priority`、`drop_duplicate`、`drop_oldest`、`block_new` 或 `none`。

## 记录要求

- event package 保存到 `benchmark/raw/05_alarm_system/<board>/events/`。
- 事件触发日志保存到 `logs/runtime/05_alarm_system/<board>/`。
- ROI 错位、抽帧失败、clip 不完整写入 `logs/failures/05_alarm_system/<board>/`。
- `projects/05_alarm_system/reports/event_pipeline.md` 必须记录规则、队列策略、ROI 策略和失败样例。

## 输出文件

| 文件 | 要求 |
|---|---|
| `benchmark/raw/05_alarm_system/<board>/events/*event_packages*.jsonl` | event package |
| `logs/runtime/05_alarm_system/<board>/*event_trigger*.log` | 触发日志 |
| `logs/failures/05_alarm_system/<board>/*event*.log` | 失败日志 |
| `projects/05_alarm_system/reports/event_pipeline.md` | 事件链路报告 |

## 验收标准

- event_id 唯一且可追溯。
- `alarm_domain`、`alarm_type`、`trigger_rule_id` 和 `trigger_reason` 与 05H 定义一致。
- ROI 坐标与源图一致。
- 关键帧、ROI、短视频片段路径存在并可引用；缺失时只能通过字段级 schema 检查，不能通过完整证据验收。
- 高频检测不被抽帧、ROI 或模型调用阻塞。
- 误触发、漏触发、队列丢弃和抽帧失败有记录。

## 降级和问题库

下面问题必须进入 `projects/05_alarm_system/reports/troubleshooting.md`：

- event_id 重复或无法追溯。
- ROI 坐标错位。
- 关键帧保存失败。
- 视频片段截取失败或不完整。
- 事件队列堆积导致告警延迟不可控。
- 误触发或漏触发影响后续 LLM/VLM 判断。
