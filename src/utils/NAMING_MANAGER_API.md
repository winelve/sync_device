# NamingManager 接口使用文档

## 概述

`NamingManager` 是一个统一的文件命名和路径管理器，用于管理录制过程中的文件命名和目录结构。它提供了完整的录制会话生命周期管理，从会话创建到文件命名，再到会话完成。

## 核心概念

### 录制会话 (Recording Session)
- 每次录制都会创建一个独立的会话
- 会话包含时间戳、输出路径和文件列表
- 会话结束时会生成完整的会话信息文件

### 文件命名规则
- **Kinect文件**: `时间戳-设备类型-设备名称.mkv`
- **音频文件**: `时间戳-设备名称.wav`
- **会话信息**: `session_info.json`

## 类初始化

```python
from src.utils.naming import NamingManager
from src.utils.config import get_config_manager

# 初始化配置管理器
config_manager = get_config_manager("./config.json")

# 创建命名管理器实例
naming_manager = NamingManager(config_manager)
```

## 主要接口函数

### 1. 创建录制会话

```python
def create_recording_session(self, custom_timestamp: str = None, mode_override: str = None) -> Dict[str, Any]
```

**功能**: 创建新的录制会话，设置输出目录和初始化会话状态

**参数**:
- `custom_timestamp`: 自定义时间戳，默认为当前时间
- `mode_override`: 模式覆盖 ("standalone" 或 "sync")

**返回值**: 包含会话信息的字典
```python
{
    "timestamp": "2025-08-14_15-30-45",
    "paths": {
        "base_dir": "recordings",
        "session_dir": "recordings/sync/2025-08-14_15-30-45",
        "mode": "sync",
        "timestamp": "2025-08-14_15-30-45"
    },
    "files_created": []
}
```

**使用示例**:
```python
# 创建默认会话（使用配置文件中的模式）
session = naming_manager.create_recording_session()

# 创建指定模式的会话
session = naming_manager.create_recording_session(mode_override="standalone")

# 使用自定义时间戳
session = naming_manager.create_recording_session(
    custom_timestamp="2025-08-14_16-00-00"
)
```

### 2. 获取Kinect输出路径

```python
def get_kinect_output_paths(self, cmd_type_str: str) -> Dict[str, str]
```

**功能**: 获取Kinect设备的输出路径配置

**参数**:
- `cmd_type_str`: 命令类型 ("master", "subordinate", "standalone")

**返回值**: 输出路径配置字典

**使用示例**:
```python
# 获取standalone模式路径
paths = naming_manager.get_kinect_output_paths("standalone")
# 返回: {"standalone": "recordings/standalone/2025-08-14_15-30-45"}

# 获取sync模式路径
paths = naming_manager.get_kinect_output_paths("master")  # 或 "subordinate"
# 返回: {"sync": "recordings/sync/2025-08-14_15-30-45"}
```

### 3. 生成Kinect文件名

```python
def generate_kinect_filename(self, cmd_type_str: str, ip: str, device_index: int) -> str
```

**功能**: 生成Kinect录制文件的标准化文件名

**参数**:
- `cmd_type_str`: 命令类型 ("master", "subordinate", "standalone")
- `ip`: 设备IP地址 ("127.0.0.1" 或 "local")
- `device_index`: 设备索引 (0, 1, 2...)

**返回值**: 生成的文件名

**使用示例**:
```python
# 生成主设备文件名
filename = naming_manager.generate_kinect_filename("master", "127.0.0.1", 0)
# 返回: "2025-08-14_15-30-45-master-master_cam.mkv"

# 生成从设备文件名
filename = naming_manager.generate_kinect_filename("subordinate", "127.0.0.1", 2)
# 返回: "2025-08-14_15-30-45-sub-left_cam.mkv"

# 生成独立模式文件名
filename = naming_manager.generate_kinect_filename("standalone", "local", 1)
# 返回: "2025-08-14_15-30-45-standalone-standalone_cam.mkv"
```

### 4. 生成音频文件名

```python
def generate_audio_filename(self, device_index: int) -> str
```

**功能**: 生成音频录制文件的标准化文件名

**参数**:
- `device_index`: 音频设备索引

**返回值**: 生成的文件名

**使用示例**:
```python
# 生成音频文件名
filename = naming_manager.generate_audio_filename(1)
# 返回: "2025-08-14_15-30-45-main_mic.wav"

filename = naming_manager.generate_audio_filename(5)
# 返回: "2025-08-14_15-30-45-backup_mic.wav"
```

### 5. 获取音频输出路径

```python
def get_audio_output_path(self) -> str
```

**功能**: 获取音频文件的输出路径

**返回值**: 音频输出路径字符串

**使用示例**:
```python
audio_path = naming_manager.get_audio_output_path()
# 返回: "recordings/sync/2025-08-14_15-30-45"
```

### 6. 完成录制会话

```python
def finalize_session(self, **metadata) -> None
```

**功能**: 完成录制会话，保存会话信息文件并清理会话状态

**参数**:
- `**metadata`: 额外的会话元数据

**使用示例**:
```python
# 完成会话并添加元数据
naming_manager.finalize_session(
    mode="sync",
    device_count=4,
    duration=10,
    notes="测试录制"
)
```

### 7. 获取当前会话信息

```python
def get_current_session_info(self) -> Dict[str, Any]
```

**功能**: 获取当前活动会话的信息

**返回值**: 当前会话信息字典，如果没有活动会话则返回None

**使用示例**:
```python
session_info = naming_manager.get_current_session_info()
if session_info:
    print(f"当前会话时间戳: {session_info['timestamp']}")
    print(f"会话目录: {session_info['paths']['session_dir']}")
    print(f"已创建文件: {len(session_info['files_created'])}")
```

### 8. 清理失败会话

```python
def cleanup_failed_session(self) -> None
```

**功能**: 清理失败或异常终止的录制会话

**使用示例**:
```python
try:
    # 录制过程...
    pass
except Exception as e:
    logger.error(f"录制失败: {e}")
    naming_manager.cleanup_failed_session()
```

## 标准使用流程

### 完整的录制会话流程

```python
from src.utils.config import get_config_manager
from src.utils.naming import NamingManager
import logging

logger = logging.getLogger(__name__)

def recording_workflow():
    try:
        # 1. 初始化
        config_manager = get_config_manager("./config.json")
        naming_manager = NamingManager(config_manager)
        
        # 2. 创建录制会话
        session = naming_manager.create_recording_session(mode_override="sync")
        logger.info(f"录制会话已创建: {session['paths']['session_dir']}")
        
        # 3. 获取输出路径配置
        kinect_paths = naming_manager.get_kinect_output_paths("master")
        audio_path = naming_manager.get_audio_output_path()
        
        # 4. 生成文件名
        kinect_master_file = naming_manager.generate_kinect_filename("master", "127.0.0.1", 0)
        kinect_sub_file = naming_manager.generate_kinect_filename("subordinate", "127.0.0.1", 2)
        audio_file = naming_manager.generate_audio_filename(1)
        
        logger.info(f"Kinect Master文件: {kinect_master_file}")
        logger.info(f"Kinect Sub文件: {kinect_sub_file}")
        logger.info(f"音频文件: {audio_file}")
        
        # 5. 执行实际录制过程
        # ... 这里是实际的录制逻辑 ...
        
        # 6. 完成会话
        naming_manager.finalize_session(
            mode="sync",
            device_count=3,
            duration=10,
            success=True
        )
        
        logger.info("录制会话已成功完成")
        
    except Exception as e:
        logger.error(f"录制过程出错: {e}")
        naming_manager.cleanup_failed_session()
        raise

if __name__ == '__main__':
    recording_workflow()
```

### 简化的使用示例

```python
# 快速开始示例
config_manager = get_config_manager("./config.json")
naming_manager = NamingManager(config_manager)

# 创建standalone会话
session = naming_manager.create_recording_session(mode_override="standalone")

# 生成文件名
kinect_file = naming_manager.generate_kinect_filename("standalone", "local", 1)
audio_file = naming_manager.generate_audio_filename(1)

# 获取路径
output_dir = naming_manager.get_audio_output_path()

print(f"录制目录: {output_dir}")
print(f"Kinect文件: {kinect_file}")
print(f"音频文件: {audio_file}")

# 完成会话
naming_manager.finalize_session(device_count=2)
```

## 注意事项

1. **会话生命周期**: 必须先调用 `create_recording_session()` 才能使用其他功能
2. **线程安全**: 当前实现不是线程安全的，在多线程环境下需要额外的同步机制
3. **错误处理**: 如果没有活动会话就调用相关方法，会抛出 `RuntimeError`
4. **文件跟踪**: 系统会自动跟踪所有生成的文件名，并在会话信息中记录
5. **目录创建**: 系统会自动创建所需的目录结构

## 与其他组件的集成

NamingManager 通常与以下组件一起使用：

- **ConfigManager**: 提供配置信息和设备命名
- **KinectMaster**: 使用生成的文件名和路径进行录制
- **AudioRecorder**: 使用音频文件名和输出路径
- **DeviceCtlSys**: 协调整个录制流程

这个设计确保了文件命名的一致性和录制会话的完整管理。
