# 多模态告警与异构检测

这是[端侧实时视频推理与多模态告警系统](../../README.md)的告警模块。服务接收帧级检测 JSONL，确认事件并按规则选择模板、文本解释、视觉复核或组合路径。

| 入口 | 用途 |
| --- | --- |
| [服务入口](scripts/service/run_alarm_service.py) | 回放检测结果、管理常驻检测进程或重放事件 |
| [规则与模型配置](configs) | Jetson、RK3588 的事件规则、模型组合、资源门槛和历史运行配置 |
| [告警 schema](configs/alarm_schema) | 事件证据、告警输出和 benchmark 行的字段约定 |
| [板端 C++ 源码](src) | TensorRT／RKNN 检测、双 DLA 变体及 RKLLM 文本与视觉服务 |
| [服务测试](scripts/service/testing) | 路由、证据读取、事实校验与检测回放 |

模型配置引用对应板端产物及实验记录。公开代码提供服务接口与配置，复跑真机实验时按目标板准备模型权重、定制运行库和 Engine。[构建与运行](../../docs/runbook.md) · [性能对照](../../docs/benchmarks.md)
