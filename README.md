# 项目五：三板边缘 LLM/VLM 告警解释系统

**Project 5: Multi-Board Edge LLM/VLM Alarm Explanation System**

## 概述

本项目在资源受限的 8GB 边缘开发板上，将实时 YOLO11n 目标检测、常驻文本 LLM 推理和异步 VLM 图文复核整合为完整的智能告警解释系统。系统不是简单回答"画面里有什么"，而是围绕检测事实完成"检测 → 事件触发 → 证据采集 → LLM/VLM 解释 → 事实守卫 → 结构化告警 JSON"的闭环，确保每条告警可追溯、可解释、可降级。

这是整个作品集的旗舰集成项目：项目一提供 YOLO11n 多后端部署基线，项目三提供 C++ 实时视频 pipeline，项目四提供 LLM/VLM 准入等级和资源边界。项目五在前序证据之上构建独立代码边界，形成可复现的端侧系统。

## 系统架构

```
摄像头 / 固定视频 / RTSP
        │
        ▼
┌──────────────────────┐
│  YOLO11n 实时检测     │  TensorRT FP16 (Jetson) / RKNN INT8 (RK3588)
│  30 FPS, 有界队列输出  │
└──────────┬───────────┘
           │ frame-level detection JSONL
           ▼
┌──────────────────────┐
│  事件触发 + 抽帧/ROI  │  类别/置信度/冷却/连续帧规则
│  证据资产生成         │  keyframe, ROI image, video clip
└──────────┬───────────┘
           │ event package
           ▼
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌──────────┐  ┌──────────────┐
│ 常驻文本  │  │ VLM 图文复核  │
│ LLM      │  │ (低频异步)    │
│ 告警归因  │  │ ROI/关键帧 QA │
│ 日志解释  │  │              │
└─────┬────┘  └──────┬───────┘
      │              │
      └──────┬───────┘
             ▼
     ┌───────────────┐
     │  Fact Guard   │  检测事实 vs LLM 解释冲突校验
     └───────┬───────┘
             ▼
     ┌───────────────┐
     │  Alarm JSON   │  结构化告警输出 + schema 校验
     └───────────────┘
```

## 硬件与模型

| 板卡 | 检测 | 文本 LLM | 图文 VLM |
|------|------|----------|----------|
| **Jetson Xavier NX 8GB** | YOLO11n + TensorRT INT8 PTQ | Qwen3-1.7B GGUF Q4_K_M (llama.cpp CUDA, 常驻) | Qwen3-VL-2B-Instruct Q4_K_M (postrun async, Route B) |
| **RK3588 8GB** | YOLO11n + RKNN INT8 | Qwen3-1.7B RKLLM W8A8 (常驻) | Qwen3-VL-2B-Instruct RKNN+RKLLM (常驻, Route A) |

| 模型 | 用途 | 准入等级 | 备注 |
|------|------|----------|------|
| YOLO11n | 实时目标检测 | 项目一/三基线 | 30 FPS 稳定 |
| Qwen3-1.7B | 文本告警归因、日志解释 | B_low_frequency | 事件触发异步调用 |
| Qwen3-VL-2B-Instruct | ROI/关键帧视觉问答 | B_low_frequency | 低频异步，不阻塞检测 |
| Gemma 3n E2B | Jetson LLM/VLM 备选 | 项目四对照 | 非主线 |
| SmolVLM2-500M | 多帧视频理解 | D_not_used | 按项目四结论禁用 |

## 核心特性

- **双板异构部署**：Jetson 采用 Route B（实时检测+文本常驻，VLM postrun 异步），RK3588 采用 Route A（检测+文本+VLM 全常驻同窗），根据各板硬件特性选择最优拓扑
- **事实守卫 (Fact Guard)**：LLM 文本解释必须通过 `fact_guard.py` 校验，检测类别冲突、置信度漂移、风险等级不匹配和未支持声明，冲突时自动替换为 detector-fact 安全文本
- **常驻模型服务**：文本 LLM 和 VLM 均以常驻进程运行，一次加载多请求复用，避免每次请求的冷启动延迟
- **有界事件队列**：`BoundedEventQueue` 限制队列深度，满时丢弃最新事件，防止 LLM/VLM 背压阻塞检测主线
- **结构化告警 JSON**：每条告警包含事件 ID、检测事实、规则触发、模型解释、证据路径和资源指标，通过 schema 校验
- **完整降级链**：LLM 超时降级为模板告警，VLM 超时跳过，视频理解按项目四结论禁用，JSON 不合格自动修复

## 验收结果

**验收状态**：`dual_board_target_pass_publishable_text_guard_pass`（2026-07-18 冻结）

**双板 Target Benchmark**（`20260717_p05_dual_board_target_v1`）：

| 指标 | Jetson | RK3588 | 验收 |
|------|-------:|-------:|------|
| 持续窗口 | 7217.22 s | 7203.72 s | 均 > 7200 s, pass |
| 检测 FPS | 30.00 | 30.04 | pass |
| 事件 / 告警数 | 1550 / 1550 | 765 / 765 | pass |
| 丢事件数 | 0 | 0 | pass |
| 真实 LLM 调用 | 2 | 2 | pass |
| 真实 VLM 调用 | postrun async 2/2 pass | resident 2/2 pass | pass |
| 双板启动偏移 | 22.5 s | - | pass |
| 有效重叠 | 7194.72 s | - | 阈值 >= 6900 s, pass |

**Fact Guard 验证**（`20260718_jetson_8gb_alarm_service_text_fact_guard_smoke_v3`）：

| 指标 | 结果 |
|------|------|
| 常驻服务 PID / 模型加载次数 | 1901315 / 1 |
| 真实 no-think 请求数 | 3 |
| 原始 LLM 事实冲突 | 3/3（原文仅审计，不直接发布） |
| 冲突替换为 detector-fact 文本 | 3/3 pass |
| Alarm JSON schema | 3/3 pass |

**Schema 证据**：

| 证据组 | event | alarm | raw benchmark | stability |
|--------|-------|-------|---------------|-----------|
| 双板 Jetson P9 | pass | pass | pass | pass |
| 双板 RK3588 P9 | pass | pass | pass | pass |
| Jetson text guard v3 | pass | pass | pass | pass |

## 快速启动

```bash
# Jetson Route B: 实时检测 + 常驻文本 + postrun async VLM
python scripts/service/run_alarm_service.py \
  --run-id <RUN_ID> \
  --board jetson_8gb \
  --environment-baseline-id <BASELINE_ID> \
  --detector-mode resident_process \
  --detector-command "<Project5 本地 TensorRT detector 命令>" \
  --detector-output <JSONL 输出路径> \
  --rules <事件规则 YAML> \
  --model-config configs/models/jetson_model_combo.yaml \
  --text-mode llama_cpp_resident \
  --text-model-path <Qwen3-1.7B GGUF 路径> \
  --vlm-mode stub \
  --stability-tier target \
  --window-sec 7200

# RK3588 Route A: 全常驻（检测 + 文本 + VLM）
python scripts/service/run_alarm_service.py \
  --run-id <RUN_ID> \
  --board rk3588_8gb \
  --environment-baseline-id <BASELINE_ID> \
  --detector-mode resident_process \
  --detector-command "<Project5 本地 RKNN detector 命令>" \
  --detector-output <JSONL 输出路径> \
  --rules <事件规则 YAML> \
  --model-config configs/models/rk3588_model_combo.yaml \
  --text-mode rkllm_resident \
  --text-model-path <Qwen3-1.7B RKLLM 路径> \
  --vlm-mode rkllm_multimodal_resident \
  --vision-model <Qwen3-VL RKNN vision 路径> \
  --decoder-model <Qwen3-VL RKLLM decoder 路径> \
  --stability-tier target \
  --window-sec 7200
```

## 目录结构

```
05_alarm_system_github/
├── configs/
│   └── models/
│       ├── jetson_model_combo.yaml      # Jetson 模型组合与准入配置
│       ├── rk3588_model_combo.yaml      # RK3588 模型组合与准入配置
│       └── model_combo_schema.yaml      # 模型组合 schema 定义
├── scripts/
│   ├── service/                         # 核心服务代码
│   │   ├── run_alarm_service.py         # 主服务入口
│   │   ├── detector_service.py          # 检测器服务（常驻/回放/事件输入）
│   │   ├── event_queue.py               # 有界事件队列
│   │   ├── text_worker.py               # 文本 LLM worker
│   │   ├── vlm_worker.py                # VLM worker
│   │   ├── asset_worker.py              # 证据资产 worker
│   │   ├── alarm_sink.py                # 告警 JSON 输出
│   │   ├── run_async_vlm_enrichment.py  # Jetson Route B 异步 VLM
│   │   ├── llama_cpp_resident_client.py # llama.cpp 常驻文本客户端
│   │   ├── llama_cpp_resident_vlm_client.py  # llama.cpp 常驻 VLM 客户端
│   │   ├── rkllm_resident_client.py     # RKLLM 常驻文本客户端
│   │   ├── rkllm_resident_vlm_client.py # RKLLM 常驻 VLM 客户端
│   │   └── testing/                     # 测试工具
│   ├── run_demo/                        # 演示与独立工具
│   │   ├── fact_guard.py                # 事实守卫（LLM 解释校验）
│   │   ├── build_alarm_json.py          # 告警 JSON 构建
│   │   ├── run_llm_explain.py           # 独立 LLM 解释
│   │   └── run_vlm_roi_qa.py            # 独立 VLM ROI 问答
│   ├── benchmark/                       # Benchmark 与验收工具
│   │   ├── run_alarm_system_benchmark.py
│   │   ├── run_alarm_stability_window.py
│   │   ├── validate_alarm_jsonl.py
│   │   ├── summarize_dual_board_window.py
│   │   └── verify_final_acceptance_manifest.py
│   ├── build/                           # 编译脚本
│   └── monitor/                         # 监控脚本
├── src/
│   ├── detector/
│   │   └── p05_detector_service.cpp     # C++ 检测器服务源码
│   ├── llm_client/
│   │   ├── rkllm_resident_text_server.cpp   # RKLLM 常驻文本服务
│   │   └── rkllm_single_turn.cpp            # RKLLM 单轮推理
│   └── vlm_client/
│       ├── rkllm_resident_vlm_server.cpp    # RKLLM 常驻 VLM 服务
│       ├── image_enc.h / image_enc.cc       # 图像编码
│       └── CMakeLists.txt
├── runners/                             # 编译产物
├── specs/                               # 项目规范文档
├── reports/                             # 验收报告与问题记录
│   ├── final_acceptance_report.md
│   ├── failure_and_fallback.md
│   ├── stability_report.md
│   └── troubleshooting.md
└── README.md
```

## 设计决策

### Route A vs Route B：为什么两块板用不同拓扑

**Jetson Route B（检测+文本常驻，VLM postrun 异步）**

Jetson 的核心问题是 CUDA/NvMap 内存竞争。当检测器、文本 LLM 和 VLM 同时常驻时，VLM 的 multimodal request path 会触发 `RemoteDisconnected` 和 `timeout`，这不是偶发现象，而是 llama.cpp CUDA 后端在 Jetson 8GB 上的系统性限制。实测数据：

- Route A（检测+VLM 常驻，文本模板）：VLM 真实请求全部 timeout
- 同窗并发（检测+文本+VLM 全常驻）：VLM 请求同样失败
- Standalone VLM：可以正常工作

结论：问题出在检测器运行时的 CUDA 内存压力与 VLM multimodal 推理的冲突。Route B 把 VLM 从实时链路拆到独立进程，在检测+文本服务结束后再执行 VLM enrichment，彻底规避了并发内存竞争。

**RK3588 Route A（全常驻同窗）**

RK3588 使用 RKLLM Runtime 和 NPU 推理，内存隔离比 Jetson 的 CUDA 共享内存模型更干净。实测中检测器、RKLLM 文本和 RKNN/RKLLM VLM 可以在同窗内稳定共存，VLM 真实请求 2/2 pass。因此 RK3588 选择全常驻拓扑，减少 VLM 调用延迟。

### 为什么用常驻模型服务

边缘设备上模型冷启动代价极高：Qwen3-1.7B 加载需要数秒到数十秒，Qwen3-VL-2B 更久。如果每次请求都重新加载模型，LLM/VLM 的调用延迟会远超检测事件间隔，导致队列堆积和事件丢失。常驻服务一次加载、多请求复用，将推理延迟从"加载+推理"降到"推理"。

验收证据：Jetson 文本常驻 `resident_server_pid=1901315, model_load_count=1, request_index=1/2/3`；RK3588 文本常驻 `resident_server_pid=2046602, model_load_count=1, request_index=1/2/3`。

### 为什么用有界队列

检测器以 30 FPS 持续输出，LLM/VLM 以低频异步消费。如果 LLM/VLM 响应变慢（p95 可达 6-57 秒），事件会在队列中堆积，最终耗尽内存。`BoundedEventQueue` 设置容量上限，满时丢弃最新事件（`drop_policy=drop_newest`），保证检测主线不被背压阻塞。验收中双板 `drop_count=0`，说明队列容量配置合理，但这个安全阀必须存在。

### 为什么需要 Fact Guard

LLM 在边缘设备上的推理质量不稳定。实测中发现 Qwen3-1.7B 会把 `vehicle_presence/car` 事件解释为"未佩戴安全帽"，即 LLM 输出了检测事实中不存在的类别和行为。这种"事实漂移"在安防场景中不可接受。`fact_guard.py` 做四项校验：

1. **未支持声明检测**：禁止出现"安全帽""跌倒""火焰"等系统未实现的业务告警
2. **类别一致性**：LLM 提及的类别必须在检测事实的 `detections` 中存在
3. **置信度校验**：LLM 引用的置信度必须与检测事实一致
4. **风险等级匹配**：LLM 输出的风险等级必须与规则判定一致

冲突时，发布文本替换为 `safe_explanation()`，即直接从检测事实生成的安全文本，原始 LLM 输出保留审计。

## 降级策略

| 故障模式 | 触发条件 | 降级动作 | 输出状态 |
|----------|----------|----------|----------|
| 视频理解不准入 | SmolVLM2 为 D_not_used | 禁用视频模型，用检测/抽帧摘要替代 | `disabled_by_project4_decision` |
| VLM 延迟过高 | Qwen3-VL 超时（Jetson p95 ~33s, RK3588 p95 ~57s） | 跳过 VLM，保留检测事实和文本解释 | `vlm_timeout` / `skip_vlm` |
| LLM 延迟不可接受 | Qwen3 超时（Jetson p95 ~6.4s, RK3588 p95 ~26.6s） | 模板告警 JSON 替代 | `llm_timeout_template` |
| VLM 图片资产缺失 | event package 无 keyframe/ROI 路径 | 不执行真实 VLM，标记阻塞 | `blocked_no_image_asset` |
| VLM 输出截断 | 多目标事件 prompt 较长 | 提高 max_tokens 到 384 | `fixed_by_max_tokens_384` |
| RKLLM 输出污染 | runtime banner 混入 stdout | 清洗 runtime 日志后写入 | `fixed_by_rkllm_output_cleanup` |
| JSON schema 不合格 | alarm JSON 校验失败 | 保留原始输出，schema repair 或模板重建 | `json_repaired` |
| 检测队列堆积 | queue_depth 超阈值 | 丢弃低优先事件，暂停 VLM，限制 LLM | `queue_degraded` |
| 摄像头/视频断流 | 输入无帧或读取错误 | 重连或切换固定视频 | `source_degraded` |
| 内存/swap 过高 | 资源超阈值 | 禁用 VLM，降低上下文和输出 token | `resource_degraded` |
| 温控/功耗异常 | 温度升高或功耗异常 | 限频低频模型，保留检测主线 | `thermal_degraded` |
| LLM 事实冲突 | Fact Guard 校验失败 | 替换为 detector-fact 安全文本 | `fact_conflict_detected` |

## 非阻塞限制

| 项目 | 当前处理 |
|------|----------|
| Jetson same-window resident VLM | 保留为诊断分支；正式方案使用 postrun async VLM enrichment |
| SmolVLM2 多帧视频理解 | 按项目四 D_not_used 禁用；只保留 detector/关键帧事实 |
| 原始 Jetson Qwen3 文本 | 不视为可直接发布；必须经过 fact_guard.py |
| 摄像头断流故障注入 | 未纳入本轮 target 必过项；后续可靠性增强应单独采证 |

## License

MIT
