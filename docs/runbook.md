# 构建与运行

以下命令从仓库根目录执行。Python 回放使用合成检测帧，可以检查事件规则、告警输出和校验；C++ 模拟后端可以检查视频流水线；真实模型需要目标板的 SDK、运行时及匹配的模型产物。

## 本机告警回放与测试

[README 的快速验证](../README.md#快速验证)会在 `runs/` 生成合成检测帧，在 `benchmark/raw/08_alarm_system/pc/` 写入事件及告警，在 `logs/runtime/08_alarm_system/pc/` 记录服务日志。合成事件覆盖 person、vehicle 和 multi-object 三种规则。

服务单测需要 OpenCV Python、NumPy 和 jsonschema。在已有 Python 3.10 及以上环境中执行：

```bash
python3 -m pip install numpy opencv-python-headless jsonschema
p=projects/08_alarm_system
python3 -m unittest discover -s "$p/scripts/service/testing"
python3 "$p/scripts/service/testing/test_fact_guard.py"
```

## C++ 模拟流水线

使用 Linux、CMake 3.16+、C++17 编译器和 OpenCV 开发库，准备一段可由 OpenCV 解码的视频：

```bash
p=projects/03_video_pipeline
cmake -S "$p" -B build/video-mock -DPIPELINE_BACKEND=mock -DCMAKE_BUILD_TYPE=Release
cmake --build build/video-mock --parallel

mkdir -p runs/video-mock
printf '%s\n' 'board_name: PC' 'target: pc' 'backend_runtime: mock' \
  'execution_provider: mock' 'precision_or_quantization: mock' \
  > runs/video-mock/backend.yaml

build/video-mock/video_pipeline_app \
  --backend-config runs/video-mock/backend.yaml \
  --input-source-type video_file --input /path/to/video.mp4 \
  --duration-sec 5 --preview-window off \
  --raw-output runs/video-mock/frames.jsonl
```

查看输出 JSONL 中的 `frame_id`、`end_to_end_latency_ms`、各阶段耗时和队列大小。模拟后端用于执行流程检查，其检测输出和耗时只代表模拟运行。

## 真机检测

| 平台 | 编译参数 | 目标板依赖 |
| --- | --- | --- |
| Jetson | `-DPIPELINE_BACKEND=tensorrt` | CUDA、TensorRT C++ 头文件与库，按板端版本生成的 `.engine` |
| RK3588 | `-DPIPELINE_BACKEND=rknn` | RKNN 头文件与 `librknnrt.so`，匹配运行时的 `.rknn` |
| RDK X5 | `-DPIPELINE_BACKEND=bpu` | Horizon DNN/HBRT，匹配 BPU 的模型产物。IMX219 输入还需要 HBN／srcampy |

板端配置记录模型路径和哈希。使用自行生成的产物时，把板卡配置复制到 `runs/` 并更新位于 `mainline_artifact` 下的路径和哈希。以下以 Jetson 单板 TensorRT GPU 检测为例：

```bash
p=projects/03_video_pipeline
cmake -S "$p" -B build/video-tensorrt -DPIPELINE_BACKEND=tensorrt -DCMAKE_BUILD_TYPE=Release
cmake --build build/video-tensorrt --parallel

mkdir -p runs/jetson-video
cp "$p/configs/boards/jetson_8gb.yaml" runs/jetson-video/backend.yaml
# Edit backend_artifact_path and backend_artifact_sha256 in backend.yaml as needed.
build/video-tensorrt/video_pipeline_app \
  --backend-config runs/jetson-video/backend.yaml \
  --model-config "$p/configs/models/yolo11n.yaml" \
  --config "$p/configs/pipeline/jetson_tensorrt_pipeline.yaml" \
  --input-source-type video_file --input /path/to/video.mp4 \
  --duration-sec 30 --preview-window off \
  --raw-output runs/jetson-video/frames.jsonl
```

迁入的[视频实验手册](../projects/03_video_pipeline/reports/runbook.md)和脚本保留原始板端实验目录与输入约定。历史命令中的模型资产、共享 schema、样本和监控环境由原实验工作区提供。上面的 CMake 与直接运行命令可用于当前仓库中独立构建。

## 双 DLA 与告警服务

在 Jetson 上编译 [双 DLA 变体](../projects/08_alarm_system/src/detector/dual_dla_detector_service.cpp)。使用分别面向 DLA0 和 DLA1 构建的两个 Engine，按 worker 顺序传入路径：

```bash
p=projects/08_alarm_system
cmake -S "$p/src/detector" -B build/detector-dual-dla \
  -DPIPELINE_BACKEND=tensorrt -DDETECTOR_DUAL_DLA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/detector-dual-dla --parallel

mkdir -p runs/jetson-dla
build/detector-dual-dla/p05_detector_service \
  --backend-config "$p/configs/detector/boards/jetson_8gb.yaml" \
  --model-config "$p/configs/detector/models/yolo11n.yaml" \
  --config "$p/configs/detector/pipeline/jetson_tensorrt_pipeline.yaml" \
  --input-source-type video_file --input /path/to/video.mp4 \
  --inference-workers 2 --postprocess-workers 2 \
  --worker-artifact-paths "/path/to/dla0.engine,/path/to/dla1.engine" \
  --duration-sec 30 --preview-window off \
  --raw-output runs/jetson-dla/frames.jsonl
```

在运行日志中查找两个 `TENSORRT_DLA_RUNTIME_CORE`，并检查帧级 `runtime_dla_core`。CMake 继续使用历史可执行文件名 `p05_detector_service`。源文件和构建开关区分了双 DLA 变体。

告警服务支持 `replay`、`resident_process` 和 `events_input`。将上述帧级 JSONL 作为 `--detector-raw` 可以先验证规则链路。实时模式使用 `--detector-command` 和 `--detector-output` 由服务启动本仓库的告警检测进程，并轮询它写出的 JSONL。查看完整参数：

```bash
python3 projects/08_alarm_system/scripts/service/run_alarm_service.py --help
```

Jetson 的真实模型模式通过 `llama_cpp_resident` 和 `llama_cpp_multimodal_resident` 接入文本 GGUF、视觉模型与 mmproj。模型组合配置引用历史运行库及哈希。要启用自己构建的 llama.cpp，请复制组合配置为本地 YAML，按运行环境指定服务器、模型和 runtime profile。

RK3588 的文本和视觉服务分别通过以下 CMake 入口构建。先将 `RKLLM_API_PATH` 设置为包含 `include/rkllm.h` 和 `aarch64/librkllmrt.so` 的 SDK 目录，设置 `RKNN_SDK_ROOT` 以供检测和视觉服务查找 RKNN。

```bash
p=projects/08_alarm_system
cmake -S "$p/src/llm_client" -B build/rkllm-text -DRKLLM_API_PATH="$RKLLM_API_PATH"
cmake --build build/rkllm-text --parallel
cmake -S "$p/src/vlm_client" -B build/rkllm-vlm -DRKLLM_API_PATH="$RKLLM_API_PATH"
cmake --build build/rkllm-vlm --parallel
```

向告警服务传入对应的 `--rkllm-runner` 和 `--rkllm-mm-resident-runner`，配合 `rkllm_resident` 和 `rkllm_multimodal_resident` 模式及各自的模型路径。[告警测试矩阵](benchmarks.md)
