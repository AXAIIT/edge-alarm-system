# 性能对照与验收记录

板端记录按照视频检测、早期双板告警、后续三模协同和事件取证展开。每项结果绑定对应输入、运行拓扑和指标定义。

## C++ 实时视频检测

| 平台与对照 | 运行条件 | 吞吐 | 帧序与时延 |
| --- | --- | ---: | --- |
| Jetson TensorRT 同步写出 A/B | INT8 PTQ，同一视频集和检测配置，对照保存输出视频开关 | 25.1158 → 30.0872 FPS | 关闭同步写出后，输出阶段从关键路径移出 |
| RK3588 RKNN 实时窗口 | 600 秒，3 个 worker，分别绑定 NPU core 0、1、2 | 30.0800 FPS | 18,048 帧，无缺帧和乱序，流水线 P95 120.08 ms |
| RDK X5，1 推理／1 后处理 | IMX219 经 HBN／srcampy，约 59 秒，关闭预览 | 20.0169 FPS | 33.46% 估算丢帧率，P95 141.94 ms |
| RDK X5，2 推理／1 后处理 | 相同采集与预览设置 | 19.9322 FPS | 推理后的队列仍有积压，P95 150.74 ms |
| RDK X5，2 推理／2 后处理 | 相同采集与预览设置 | 30.0847 FPS | 无丢帧、无帧号空洞，P95 165.17 ms |

RDK X5 的 2/2 配置提高持续处理能力，同时增加已完成帧的 P95 时延。吞吐衡量单位时间内输出的帧数，时延衡量单帧从采集到输出所需时间。两项指标分别报告。

稳定性记录包括 Jetson 视频回放 **7,196 秒**、RDK X5 IMX219 **7,198 秒**、RK3588 相机与视频各 **4 小时**。RK3588 视频段有 5 处帧号空洞、共缺 8 帧，未发现倒序。RDK X5 记录了真实输入断连时的 `INPUT_DISCONNECTED` 和退出码 11。[流水线对照与逐项 Run ID](../projects/03_video_pipeline/reports/runtime_benchmark.md) · [稳定性记录](../projects/03_video_pipeline/reports/stability_report.md) · [故障验证](../projects/03_video_pipeline/reports/failure_and_fallback.md)

## 早期双板告警验收

| 指标 | Jetson | RK3588 |
| --- | ---: | ---: |
| 告警服务运行窗口 | 7,217.22 s | 7,203.72 s |
| 检测吞吐 | 30.000887 FPS | 30.042395 FPS |
| 事件数／告警数 | 1,550／1,550 | 765／765 |
| 事件丢弃 | 0 | 0 |
| 真实文本调用 | 2 次 | 2 次 |
| 真实视觉调用 | 检测窗口结束后异步复核，2/2 通过 | 与检测同窗低频调用，2/2 通过 |

两板有效重叠窗口为 **7,194.72 秒**。少量文本和视觉调用验证了真实模型链路。独立文本发布检查中，3 条与检测事实冲突的原始输出均由规则说明替换，告警结构校验 3/3 通过。[实验编号、拓扑与验收条件](../reports/final_acceptance_report.md)

## Jetson 异构与三模协同

| 问题 | 对照 | 观测与决策 |
| --- | --- | --- |
| DLA 层覆盖与运行成本 | 整图 DLA0 + GPU fallback 对比 DLA 骨干 + GPU attention／neck／head | Engine-only 吞吐 23.14 → 40.62 qps。分区切换、Reformat 和 CPU 外置后处理均需在流水线中单独度量 |
| 双 DLA 的实际使用 | 分别加载 DLA0/DLA1 Engine，运行时显式绑定核心，跟踪结果重排 | 两个核心的装载和输出均可验证；检测吞吐仍受检测尾部与并发模型负载影响 |
| 真实三模同窗 | `20261012_jetson_8gb_project08_latest_off_vlm_visual_gpu_natural_triad_v2`，两轮分别 619.20、618.92 秒 | 按有效帧输出时间跨度计算 28.82、28.79 FPS。LLM 6/6 返回，VLM 6/7 返回。3 次 VLM 请求被内存门控拒绝；完整质量、资源与 30 FPS 验收未通过 |
| 固定样本调度 | `20261022_jetson_8gb_project08_system_contention_v1`，固定模型和输入，对照 CPU 运行线程策略 | 保守候选的 LLM Client 均值 13.45 → 11.99 秒（−10.89%）。另一五线程候选在自然窗发生 VLM CUDA OOM，仅保留为实验记录 |

三模同窗的 **LLM 6/6 返回**中，严格质量校验通过 1 次，其余 5 次使用规则解释。VLM 的 7 次实际请求有一次上下文超限，资源门控拒绝发生在发起请求前。后续实验把语言层和 KV 放在 CPU、视觉编码放在 GPU，设备归因来自模型配置、加载日志和进程证据。

本仓库提供 [双 DLA 检测源码](../projects/08_alarm_system/src/detector/dual_dla_detector_service.cpp) 和 [Jetson 模型配置](../projects/08_alarm_system/configs/models/jetson_model_combo.yaml)。重建历史窗口需要对应 Engine、模型、定制 runtime、视频输入和环境快照。

## 事件索引供图

配对实验 `20261013_jetson_8gb_project08_indexed_event_assets_triad_v1` 覆盖 7 个事件，每组各 3 次。固定取图目标、裁剪策略和 JPEG 参数，分别使用顺序读取和预建索引读取。索引保存解码序号、时间戳和关键帧位置，绑定源视频哈希与解码器身份。

| 指标 | 顺序读取 | 预建索引读取 |
| --- | ---: | ---: |
| 完整取证平均耗时 | 2,504.03 ms | 701.02 ms |
| 完整取证 P95 | 3,881.59 ms | 874.57 ms |
| 图像一致性 | 201 个 JPEG 作为对照 | 201 个逐一字节一致 |

该对照包含读帧、裁剪和写 JPG，使用已建立的索引。首次建立 20 段视频索引另花费约 65.6 秒。自然事件三模窗口观察到取证开销下降，模型调用内容和输出长度仍随事件变化。[索引与帧身份校验实现](../projects/08_alarm_system/scripts/service/indexed_video_reader.py)
