# 项目五环境基线模板

项目五环境基线用于固定检测 runtime、LLM/VLM runtime、输入源、服务环境、监控工具和稳定性条件。环境基线一旦影响 benchmark 可比性，就必须新建。

推荐路径：

```text
projects/05_alarm_system/runs/<yyyymmdd>_<target>_env_baseline/run.md
```

```yaml
environment_baseline_id:
date:
target: jetson_8gb | rk3588_8gb | pc
mainline_target_allowed:
  - jetson_8gb
  - rk3588_8gb
board:
status: pass | fail | blocked | not_verified

system:
  os:
  kernel:
  memory_gb:
  storage:
  swap_enabled:
  swap_size_mb:
  power_mode:
  cooling:
  cpu_governor:

vision_runtime:
  detector_backend:
  tensorrt_version:
  rknn_runtime_version:
  bpu_runtime_version: not_applicable_for_project5_mainline
  opencv_version:
  gstreamer_version:
  ffmpeg_version:

llm_vlm_runtime:
  python_version:
  pytorch_version:
  transformers_version:
  llama_cpp_commit:
  rkllm_runtime_version:
  hobot_runtime_version: not_applicable_for_project5_mainline
  tokenizer_runtime:
  model_runner_versions:

service_env:
  service_manager:
  service_name:
  docker:
  systemd:
  restart_policy:
  network:
  camera_devices:
  rtsp_reachability:
  healthcheck_command:

monitor_tools:
  cpu:
  gpu:
  npu:
  bpu: not_applicable_for_project5_mainline
  memory:
  swap:
  temperature:
  power:
  queue_metrics:
  unavailable_metrics:
    - metric:
      reason:
      fallback_evidence:

logs:
  environment_probe_log:
  monitor_probe_log:
  service_probe_log:
```

## 记录要求

- 05A/05B/05F 的正式 run 必须引用环境基线 ID。
- 项目五正式主线只允许 `jetson_8gb` 和 `rk3588_8gb`；`pc` 只能用于脚本调试、CPU baseline 或接口联调，不能进入双板正式 selected run。
- RDK X5 已从项目五主线移除。`bpu_runtime_version`、`hobot_runtime_version` 和 `monitor_tools.bpu` 只能写 `not_applicable_for_project5_mainline` 或作为历史证据引用，不能重新引入项目五正式实验。
- 如果 power mode、swap、散热、runtime、驱动、容器或服务管理方式变化，必须重新建立环境基线。
- 不可观测指标必须写入 `unavailable_metrics`，不能从报告中静默删除。
