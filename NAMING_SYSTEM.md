# 文件命名和路径管理系统

## 概述

本系统实现了统一的文件命名和路径管理，解决了之前代码中文件命名混乱和路径管理分散的问题。新系统采用工程化的设计思路，提供了清晰的目录结构和有意义的文件命名。

## 主要特性

### 🏗️ 统一的目录结构
```
recordings/
├── sync/              # 同步模式录制
│   └── 时间戳/
│       ├── 时间戳-master-设备名.mkv
│       ├── 时间戳-sub-设备名.mkv
│       ├── 时间戳-音频设备名.wav
│       └── session_info.json
└── standalone/        # 独立模式录制
    └── 时间戳/
        ├── 时间戳-standalone-设备名.mkv
        ├── 时间戳-音频设备名.wav
        └── session_info.json
```

### 📝 有意义的文件命名
- **旧系统**: `master-2025-08-14_15-30-45-device0.mkv`
- **新系统**: `2025-08-14_15-30-45-master-master_cam.mkv`

### 🔧 灵活的设备命名配置
```json
{
  "kinect": {
    "device_names": {
      "127.0.0.1": {
        "0": "master_cam",
        "2": "left_cam",
        "3": "right_cam"
      },
      "local": {
        "1": "standalone_cam"
      }
    }
  },
  "audio": {
    "device_names": {
      "1": "main_mic",
      "5": "backup_mic",
      "6": "wireless_mic"
    }
  }
}
```

### 📊 自动生成会话信息
每次录制会自动生成 `session_info.json`，包含：
- 录制时间和配置
- 参与录制的设备信息
- 生成的文件列表
- 会话元数据

## 核心组件

### 1. ConfigManager (src/config.py)
- **功能**: 统一配置管理
- **新增方法**:
  - `create_session_directory()`: 创建录制会话目录
  - `get_device_name()`: 获取设备友好名称
  - `create_session_info()`: 生成会话信息文件

### 2. NamingManager (src/naming.py)
- **功能**: 文件命名和路径管理
- **核心方法**:
  - `create_recording_session()`: 创建录制会话
  - `generate_kinect_filename()`: 生成Kinect文件名
  - `generate_audio_filename()`: 生成音频文件名
  - `finalize_session()`: 完成会话并保存信息

### 3. 更新的主要文件
- **main.py**: 集成命名管理器
- **kinect_record_master.py**: 支持新的命名系统
- **audiorec.py**: 支持设备友好命名

## 使用方法

### 基本使用
```python
from src.utils.config import get_config_manager
from src.main import DeviceCtlSys

# 初始化配置
config_manager = get_config_manager("./config.json")

# 创建控制系统
controller = DeviceCtlSys(config_manager)

# 开始录制（自动创建目录和命名文件）
controller.start_recording()
```

### 自定义设备命名
```python
# 更新设备命名
config_manager.update_config("kinect", {
    "device_names": {
        "192.168.1.100": {
            "0": "front_camera",
            "1": "back_camera"
        }
    }
})
```

### 修改输出路径
```python
# 自定义录制根目录
config_manager.update_config("recording", {
    "base_output_dir": "custom_recordings"
})
```

## 配置说明

### 录制配置新增项
- `base_output_dir`: 录制文件根目录（默认："recordings"）
- `timestamp_format`: 时间戳格式（默认："%Y-%m-%d_%H-%M-%S"）

### 设备命名配置
- **Kinect设备**: `kinect.device_names`
- **音频设备**: `audio.device_names`

## 测试和演示

### 运行测试
```bash
# 测试命名系统
python test_naming.py

# 查看配置信息
python demo.py config

# 测试录制模式（需要设备）
python demo.py standalone
python demo.py sync
```

### 测试结果示例
```
录制会话: recordings/sync/2025-08-14_15-30-45/
├── 2025-08-14_15-30-45-master-master_cam.mkv
├── 2025-08-14_15-30-45-sub-left_cam.mkv
├── 2025-08-14_15-30-45-sub-right_cam.mkv
├── 2025-08-14_15-30-45-main_mic.wav
└── session_info.json
```

## 优势对比

### 旧系统问题
- ❌ 文件命名混乱 (`master-时间戳-device0.mkv`)
- ❌ 路径管理分散在各个模块
- ❌ 硬编码的目录结构
- ❌ 缺少录制会话信息

### 新系统优势
- ✅ 统一的文件命名规则
- ✅ 集中的路径管理
- ✅ 可配置的设备命名
- ✅ 自动的会话管理
- ✅ 完整的录制元数据
- ✅ 工程化的代码结构

## 向后兼容性

新系统保持了与现有代码的兼容性：
- 所有原有的配置参数仍然有效
- 保留了旧的命名方式作为后备方案
- 现有的录制流程无需修改

## 文档

- **CONFIG.md**: 详细的配置文件说明
- **demo.py**: 使用示例和演示
- **test_naming.py**: 功能测试脚本

这个新的命名系统提供了更好的文件组织、更清晰的命名规则和更强的可配置性，同时保持了代码的整洁和可维护性。
