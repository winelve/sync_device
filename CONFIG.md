# 配置文件说明 (config.json)

此文件用于配置整个设备录制系统的所有参数。系统启动时会自动加载此配置文件。

## 文件结构规范

系统将自动创建如下目录结构：

```
recordings/
├── sync/
│   ├── 时间戳1/
│   │   ├── 时间戳-master-设备名.mkv
│   │   ├── 时间戳-sub-设备名.mkv
│   │   ├── 时间戳-sub-设备名.mkv
│   │   ├── 时间戳-音频设备名.wav
│   │   └── session_info.json
│   ├── 时间戳2/
│   └── ...
└── standalone/
    ├── 时间戳1/
    │   ├── 时间戳-standalone-设备名.mkv
    │   ├── 时间戳-音频设备名.wav
    │   └── session_info.json
    └── ...
```

## 配置结构

### recording (录制总体配置)
- `mode`: 系统级录制模式
  - `"standalone"`: 独立模式，单设备录制
  - `"sync"`: 同步模式，多设备同步录制
- `duration`: 录制时长（秒）- **所有设备统一使用此时长**
- `standalone_delay`: 独立模式下音频录制延迟启动时间（秒）
- `sync_delay`: 同步模式下音频录制延迟启动时间（秒）
- `is_local_debug`: 是否为本地调试模式（true/false）
- `base_output_dir`: 录制文件根目录（默认："recordings"）
- `timestamp_format`: 时间戳格式（默认："%Y-%m-%d_%H-%M-%S"）

### kinect (Kinect设备配置)
基于 k4arecorder 命令行工具的参数：

- `"--device"`: 主设备索引（数字，默认0为第一个设备）
- `"-c"`: 彩色相机分辨率，可选值：
  - `"3072p"`, `"2160p"`, `"1536p"`, `"1440p"`, `"1080p"`, `"720p"`, `"720p_NV12"`, `"720p_YUY2"`, `"OFF"`
- `"-d"`: 深度相机模式，可选值：
  - `"NFOV_2X2BINNED"` (窄视野2x2像素合并)
  - `"NFOV_UNBINNED"` (窄视野未合并) 
  - `"WFOV_2X2BINNED"` (广视野2x2像素合并)
  - `"WFOV_UNBINNED"` (广视野未合并)
  - `"PASSIVE_IR"` (被动红外)
  - `"OFF"` (关闭)
- `"--depth-delay"`: 彩色帧与深度帧时间偏移（微秒，负值表示深度帧先于彩色帧）
- `"-r"`: 相机帧率，可选值：`30`, `15`, `5`
- `"--imu"`: 惯性测量单元，可选值：`"ON"`, `"OFF"`
- `"--sync-delay"`: 主从相机间同步延迟（微秒，仅在从设备模式下有效）
- `"-e"`: RGB相机手动曝光值（范围：-11到1，或自动曝光）
- `"--ip-devices"`: IP到设备索引映射（仅同步模式使用）
  - 格式: `{"IP地址": [设备索引数组]}`
  - 例如: `{"127.0.0.1": [0, 2, 3], "192.168.1.100": [1, 2]}`
- `"device_names"`: **设备友好名称映射**
  - 格式: `{"IP地址": {"设备索引": "设备名称"}}`
  - 例如: `{"127.0.0.1": {"0": "master_cam", "2": "left_cam", "3": "right_cam"}, "local": {"1": "standalone_cam"}}`
  - 用于生成更有意义的文件名，替代默认的设备索引

**注意**: 以下参数由系统自动生成，无需在配置中设置：
- `"-l"` (--record-length): 由 `recording.duration` 自动设置
- `"--external-sync"`: 由系统根据录制模式和设备角色自动设置
  - 独立模式: `"Standalone"`
  - 同步模式主设备: `"Master"`  
  - 同步模式从设备: `"Subordinate"`
- `"output"`: 输出路径由系统动态设置

### audio (音频录制配置)
- `format`: 音频格式（8=最低质量，4=中等质量，2=最高质量）
- `channels`: 声道数（1=单声道，2=立体声）
- `rate`: 采样率（Hz，如 44100, 48000）
- `is_input`: 是否为输入设备（通常为 true）
- `input_device_index`: 输入设备索引数组
  - 例如: `[1]` 表示使用设备索引1
  - 可以指定多个设备: `[1, 5, 6]`
- `frames_per_buffer`: 每帧缓冲区大小（1024是常用值）
- `mode`: 录制模式
  - `"timing"`: 定时录制（推荐）
  - `"manual"`: 手动控制录制
- `"device_names"`: **音频设备友好名称映射**
  - 格式: `{"设备索引": "设备名称"}`
  - 例如: `{"1": "main_mic", "5": "backup_mic", "6": "wireless_mic"}`
  - 用于生成更有意义的文件名

**注意**: 以下参数由系统自动生成，无需在配置中设置：
- `timing`: 由 `recording.duration` 自动设置
- `outpath`: 输出路径由系统动态设置
- `filename`: 文件名模板由系统动态设置

## 文件命名规则

系统采用统一的文件命名规则：

### Kinect设备文件
- **格式**: `时间戳-设备类型-设备名称.mkv`
- **独立模式**: `2025-08-14_15-30-45-standalone-standalone_cam.mkv`
- **同步模式主设备**: `2025-08-14_15-30-45-master-master_cam.mkv`
- **同步模式从设备**: `2025-08-14_15-30-45-sub-left_cam.mkv`

### 音频设备文件
- **格式**: `时间戳-设备名称.wav`
- **示例**: `2025-08-14_15-30-45-main_mic.wav`

### 会话信息文件
- **文件名**: `session_info.json`
- **内容**: 包含完整的录制配置、设备信息和会话元数据
- **位置**: 每个录制会话目录根目录

## 使用说明

1. **修改设备命名**: 在配置文件中的 `device_names` 部分添加或修改设备名称
2. **自定义输出路径**: 修改 `recording.base_output_dir` 配置项
3. **时间戳格式**: 修改 `recording.timestamp_format` 配置项（Python strftime格式）
4. **自动目录创建**: 系统会自动创建所有必要的目录结构

## 使用说明

1. **首次使用**: 运行 `python main.py` 时，如果 config.json 不存在，系统会自动创建默认配置文件

2. **修改配置**: 直接编辑 config.json 文件即可，下次运行时会自动加载新配置

3. **查看音频设备**: 运行 `python mc87/audiorec.py` 查看可用的音频设备索引

4. **配置音频设备**: 将查看到的设备索引填入 `audio.input_device_index` 数组中

5. **配置IP设备**: 在 `kinect."--ip-devices"` 中配置远程设备的IP和对应的设备索引

## 配置示例

### 独立模式配置
```json
{
  "recording": {
    "mode": "standalone",
    "duration": 30,
    "standalone_delay": 0
  }
}
```

### 同步模式配置
```json
{
  "recording": {
    "mode": "sync",
    "duration": 60,
    "sync_delay": 0.86,
    "is_local_debug": false
  },
  "kinect": {
    "--ip-devices": {
      "192.168.1.100": [0, 1],
      "192.168.1.101": [2, 3]
    }
  }
}
```

### 多音频设备配置
```json
{
  "audio": {
    "input_device_index": [6, 7, 8],
    "channels": 2
  }
}
```

## 注意事项

1. 配置文件必须是有效的JSON格式
2. 数字类型不要加引号，布尔值使用 true/false（小写）
3. 修改配置后无需重启系统，直接运行即可
4. 如果配置文件损坏，删除它重新运行程序会创建新的默认配置
5. recording.duration 会自动同步到 kinect."-l" 和 audio.timing
