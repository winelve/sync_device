import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器，统一管理所有设备的配置"""
    
    def __init__(self, config_path: str = "./config.json"):
        self.config_path = config_path
        self._default_config = self._get_default_config()
        self.config = self._load_or_create_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "recording": {
                "mode": "sync",  # 系统级录制模式: 'standalone' 或 'sync'
                "duration": 10,  # 录制时长（秒）- 所有设备统一时长
                "standalone_delay": 0,  # 独立模式下音频录制延迟启动时间（秒）
                "sync_delay": 0.86,  # 同步模式下音频录制延迟启动时间（秒）
                "is_local_debug": True,  # 是否为本地调试模式
                "base_output_dir": "recordings",  # 录制文件根目录
                "timestamp_format": "%Y-%m-%d_%H-%M-%S"  # 时间戳格式
            },
            "kinect": {
                "--device": 1,  # 主设备索引
                "-c": "720p",  # 彩色相机分辨率: 3072p/2160p/1536p/1440p/1080p/720p/720p_NV12/720p_YUY2/OFF
                "-d": "NFOV_UNBINNED",  # 深度相机模式: NFOV_2X2BINNED/NFOV_UNBINNED/WFOV_2X2BINNED/WFOV_UNBINNED/PASSIVE_IR/OFF
                "--depth-delay": 0,  # 彩色帧与深度帧时间偏移（微秒）
                "-r": 15,  # 相机帧率: 30/15/5
                "--imu": "OFF",  # 惯性测量单元: ON/OFF
                "--sync-delay": 200,  # 主从相机间同步延迟（微秒，仅从设备模式有效）
                "-e": 1,  # RGB相机手动曝光值: -11到1，或自动曝光
                "--ip-devices": {
                    "127.0.0.1": [0, 2, 3]  # IP到设备索引的映射（仅同步模式使用）
                },
                "device_names": {
                    # 设备命名映射: IP -> {设备索引: 设备名称}
                    "127.0.0.1": {
                        "0": "master_cam",
                        "2": "left_cam", 
                        "3": "right_cam"
                    },
                    "local": {
                        "1": "standalone_cam"  # 独立模式设备命名
                    }
                }
                # 注意: --external-sync 和 -l 参数由系统根据 recording 配置自动生成
                # 注意: output 路径由系统动态设置
            },
            "audio": {
                "format": 8,  # 音频格式 (8,4,2 --> 质量逐渐升高)
                "channels": 1,  # 通道数量
                "rate": 44100,  # 采样率
                "is_input": True,  # 是否为输入设备
                "input_device_index": [1],  # 输入设备索引列表
                "frames_per_buffer": 1024,  # 每帧样本数
                "mode": "timing",  # 录制模式: 'timing'(定时) 或 'manual'(手动)
                "device_names": {
                    # 音频设备命名映射: {设备索引: 设备名称}
                    "1": "main_mic",
                    "5": "backup_mic",
                    "6": "wireless_mic"
                }
                # 注意: timing/outpath/filename 参数由系统根据 recording 配置自动生成
            }
        }
    
    def _load_or_create_config(self) -> Dict[str, Any]:
        """加载或创建配置文件"""
        if os.path.exists(self.config_path):
            try:
                logger.info(f"加载配置文件: {self.config_path}")
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 合并默认配置和加载的配置
                    merged_config = self._merge_config(self._default_config, loaded_config)
                    logger.info("配置文件加载成功")
                    return merged_config
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                logger.info("使用默认配置")
                return self._default_config.copy()
        else:
            try:
                logger.info(f"配置文件不存在，创建默认配置: {self.config_path}")
                self._save_config(self._default_config)
                logger.info("默认配置文件创建成功")
                return self._default_config.copy()
            except Exception as e:
                logger.error(f"创建配置文件失败: {e}")
                logger.info("使用默认配置（内存中）")
                return self._default_config.copy()
    
    def _merge_config(self, default: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并配置，以加载的配置为优先"""
        merged = default.copy()
        
        for key, value in loaded.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_config(merged[key], value)
            else:
                merged[key] = value
        
        return merged
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """保存配置到文件"""
        # 确保目录存在
        config_dir = os.path.dirname(os.path.abspath(self.config_path))
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get_recording_config(self) -> Dict[str, Any]:
        """获取录制配置"""
        return self.config["recording"]
    
    def get_kinect_config(self) -> Dict[str, Any]:
        """获取Kinect配置，自动生成运行时参数"""
        kinect_config = self.config["kinect"].copy()
        recording_config = self.config["recording"]
        
        # 自动设置录制时长
        kinect_config["-l"] = recording_config["duration"]
        
        # 自动设置输出路径（将在运行时由 DeviceCtlSys 设置）
        kinect_config["output"] = {}
        
        # 注意: --external-sync 参数不在这里设置，而是在 parse_cmd 函数中
        # 根据 CmdType 自动生成，避免配置冲突
        
        return kinect_config
    
    def get_audio_config(self) -> Dict[str, Any]:
        """获取音频配置，自动生成运行时参数"""
        audio_config = self.config["audio"].copy()
        recording_config = self.config["recording"]
        
        # 自动设置录制时长
        audio_config["timing"] = recording_config["duration"]
        
        # 自动设置运行时参数（将在运行时由 DeviceCtlSys 设置）
        audio_config["outpath"] = ""
        audio_config["filename"] = ""
        
        return audio_config
    
    def update_config(self, section: str, updates: Dict[str, Any]) -> None:
        """更新配置的某个部分"""
        if section in self.config:
            if isinstance(self.config[section], dict):
                self.config[section].update(updates)
            else:
                self.config[section] = updates
        else:
            self.config[section] = updates
        
        logger.debug(f"配置已更新: {section}")
    
    def save_current_config(self) -> None:
        """保存当前配置到文件"""
        try:
            self._save_config(self.config)
            logger.info(f"配置已保存到: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def get_full_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self.config.copy()
    
    def reload_config(self) -> None:
        """重新加载配置文件"""
        logger.info("重新加载配置文件")
        self.config = self._load_or_create_config()

    def create_session_directory(self, timestamp: str, mode_override: str = None) -> Dict[str, str]:
        """创建录制会话目录结构并返回路径信息"""
        recording_config = self.config["recording"]
        base_dir = recording_config.get("base_output_dir", "recordings")
        mode = mode_override if mode_override else recording_config["mode"]
        
        # 创建会话目录
        session_dir = os.path.join(base_dir, mode, timestamp)
        os.makedirs(session_dir, exist_ok=True)
        
        logger.info(f"创建录制会话目录: {session_dir}")
        
        return {
            "base_dir": base_dir,
            "session_dir": session_dir,
            "mode": mode,
            "timestamp": timestamp
        }
    
    def get_device_name(self, device_type: str, ip: str, device_index: int) -> str:
        """获取设备友好名称"""
        if device_type == "kinect":
            device_names = self.config["kinect"].get("device_names", {})
            if ip in device_names and str(device_index) in device_names[ip]:
                return device_names[ip][str(device_index)]
            # 如果找不到自定义名称，使用默认格式
            return f"kinect_{ip}_{device_index}" if ip != "local" else f"kinect_{device_index}"
        
        elif device_type == "audio":
            device_names = self.config["audio"].get("device_names", {})
            if str(device_index) in device_names:
                return device_names[str(device_index)]
            # 如果找不到自定义名称，使用默认格式
            return f"audio_{device_index}"
        
        return f"{device_type}_{device_index}"
    
    def generate_filename(self, device_type: str, timestamp: str, ip: str = "local", 
                         device_index: int = 0, file_extension: str = ".mkv") -> str:
        """生成标准化的文件名"""
        device_name = self.get_device_name(device_type, ip, device_index)
        return f"{timestamp}-{device_name}{file_extension}"
    
    def create_session_info(self, session_dir: str, timestamp: str, **kwargs) -> None:
        """创建会话信息文件"""
        recording_config = self.get_recording_config()
        
        # 精简的kinect配置，只保留关键参数
        kinect_config = self.config["kinect"]
        kinect_info = {
            "--device": kinect_config.get("--device"),
            "-c": kinect_config.get("-c"),
            "-r": kinect_config.get("-r"),
            "--imu": kinect_config.get("--imu"),
            "-e": kinect_config.get("-e"),
            "device_names": kinect_config.get("device_names", {})
        }
        # 只有在sync模式下才包含sync相关参数
        if recording_config.get("mode") == "sync":
            kinect_info["--sync-delay"] = kinect_config.get("--sync-delay")
            kinect_info["--ip-devices"] = kinect_config.get("--ip-devices", {})
        
        # 精简的音频配置，只保留关键参数
        audio_config = self.config["audio"]
        audio_info = {
            "mode": audio_config.get("mode"),
            "device_names": audio_config.get("device_names", {})
        }
        
        session_info = {
            "timestamp": timestamp,
            "recording_config": {
                "mode": recording_config["mode"],
                "duration": recording_config["duration"],
                "base_output_dir": recording_config.get("base_output_dir", "recordings")
            },
            "kinect_config": kinect_info,
            "audio_config": audio_info,
            "session_metadata": kwargs
        }
        
        session_file = os.path.join(session_dir, "session_info.json")
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2, ensure_ascii=False)
            logger.info(f"会话信息已保存: {session_file}")
        except Exception as e:
            logger.error(f"保存会话信息失败: {e}")
    
    def get_timestamp_format(self) -> str:
        """获取时间戳格式"""
        return self.config["recording"].get("timestamp_format", "%Y-%m-%d_%H-%M-%S")


# 全局配置管理器实例（仅在main.py中使用）
_config_manager = None

def get_config_manager(config_path: str = "./config.json") -> ConfigManager:
    """获取配置管理器实例（单例模式）"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
