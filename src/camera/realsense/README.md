# RealSense D405 录制模块使用说明

## 概述

这是一个简化的 RealSense D405 录制接口，支持同时录制深度和彩色数据。使用 `pyrealsense2` 库实现。

## 特性

- ✅ 同时录制深度和彩色数据
- ✅ 简化的配置接口（只暴露核心参数）
- ✅ 支持定时录制和手动控制
- ✅ 自动生成时间戳文件名
- ✅ 设备检测和分辨率查询功能

## 安装依赖

```bash
pip install pyrealsense2
```

## 快速开始

### 方式1: 快速录制（推荐用于简单场景）

```python
from camera.realsense.realsense_record import quick_record

# 录制 10 秒，使用默认配置（640x480 @ 30fps）
output_path = quick_record(
    duration=10,
    output_dir="./recordings"
)
print(f"录制完成: {output_path}")
```

### 方式2: 使用录制器类（可手动控制）

```python
from camera.realsense.realsense_record import RealSenseRecorder

# 创建录制器
recorder = RealSenseRecorder(
    width=640,
    height=480,
    fps=30,
    output_dir="./recordings"
)

# 开始录制（阻塞式，自动停止）
recorder.start_recording(duration=10)

# 或者手动控制
recorder.start_recording()  # 开始录制
# ... 做其他事情 ...
recorder.stop_recording()   # 手动停止
```

## 核心参数说明

### RealSenseRecorder 初始化参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `width` | int | 640 | 分辨率宽度 |
| `height` | int | 480 | 分辨率高度 |
| `fps` | int | 30 | 帧率 |
| `output_dir` | str | "./recordings" | 输出目录 |
| `enable_depth` | bool | True | 是否启用深度流 |
| `enable_color` | bool | True | 是否启用彩色流 |

### start_recording 方法参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `duration` | float | None | 录制时长（秒），None 表示手动停止 |
| `filename` | str | None | 输出文件名，None 则自动生成时间戳文件名 |

## 常用分辨率配置

### D405 推荐配置

```python
# 高质量配置
recorder = RealSenseRecorder(width=1280, height=720, fps=30)

# 标准配置（推荐）
recorder = RealSenseRecorder(width=640, height=480, fps=30)

# 高帧率配置
recorder = RealSenseRecorder(width=640, height=480, fps=60)

# 低延迟配置
recorder = RealSenseRecorder(width=424, height=240, fps=90)
```

## 实用工具函数

### 列出所有设备

```python
from camera.realsense.realsense_record import RealSenseRecorder

devices = RealSenseRecorder.list_devices()
for device in devices:
    print(f"设备 {device['index']}: {device['name']}")
    print(f"  序列号: {device['serial']}")
    print(f"  固件版本: {device['firmware']}")
```

### 查询支持的分辨率

```python
from camera.realsense.realsense_record import RealSenseRecorder

resolutions = RealSenseRecorder.get_supported_resolutions(device_index=0)
print("深度流支持的分辨率:")
for width, height, fps in resolutions['depth']:
    print(f"  {width}x{height} @ {fps}fps")

print("彩色流支持的分辨率:")
for width, height, fps in resolutions['color']:
    print(f"  {width}x{height} @ {fps}fps")
```

## 完整示例

```python
import logging
from camera.realsense.realsense_record import RealSenseRecorder

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 1. 检测设备
print("检测 RealSense 设备...")
devices = RealSenseRecorder.list_devices()

if not devices:
    print("未检测到设备")
    exit(1)

# 2. 查看支持的分辨率
resolutions = RealSenseRecorder.get_supported_resolutions(0)
print(f"找到 {len(resolutions['depth'])} 个深度分辨率")
print(f"找到 {len(resolutions['color'])} 个彩色分辨率")

# 3. 创建录制器
recorder = RealSenseRecorder(
    width=640,
    height=480,
    fps=30,
    output_dir="./my_recordings"
)

# 4. 开始录制
print("开始录制...")
output_path = recorder.start_recording(
    duration=10,
    filename="test_recording"
)

print(f"录制完成: {output_path}")
```

## 输出文件格式

录制的文件以 `.bag` 格式保存（RealSense 专用格式），包含：
- 深度数据流（如果启用）
- 彩色数据流（如果启用）
- 时间戳和元数据

### 播放录制文件

可以使用 RealSense Viewer 或编程方式播放 `.bag` 文件：

```python
import pyrealsense2 as rs

# 创建 pipeline
pipeline = rs.pipeline()
config = rs.config()

# 从文件读取
config.enable_device_from_file("recording.bag")

# 开始播放
pipeline.start(config)

try:
    while True:
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        
        # 处理帧数据...
        
except KeyboardInterrupt:
    pass
finally:
    pipeline.stop()
```

## 注意事项

1. **USB 连接**：确保使用 USB 3.0 或更高版本接口
2. **权限问题**：Windows 下可能需要管理员权限
3. **驱动安装**：确保已安装 RealSense SDK 和驱动
4. **磁盘空间**：录制文件较大，注意磁盘空间
   - 640x480@30fps 约 30-50 MB/秒
   - 1280x720@30fps 约 100-150 MB/秒

## 故障排除

### 找不到设备

```bash
# 检查设备连接
rs-enumerate-devices

# 或在 Python 中
from camera.realsense.realsense_record import RealSenseRecorder
RealSenseRecorder.list_devices()
```

### 不支持的分辨率

使用 `get_supported_resolutions()` 查询设备支持的分辨率，然后选择合适的配置。

### 录制卡顿

- 降低分辨率或帧率
- 确保使用 USB 3.0 接口
- 关闭其他占用 USB 带宽的设备
- 使用 SSD 存储录制文件

## 高级配置

如需更多高级功能（如后处理滤波器、对齐、预设配置等），可以直接修改 `RealSenseRecorder` 类内部实现。当前版本隐藏了这些高级选项以简化接口。
