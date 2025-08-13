"""
文件命名和路径管理模块
统一管理录制过程中的文件命名和目录结构
"""

import os
import time
import logging
from typing import Dict, List, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)

class RecordingMode(Enum):
    """录制模式枚举"""
    STANDALONE = "standalone"
    SYNC = "sync"

class DeviceType(Enum):
    """设备类型枚举"""
    KINECT = "kinect"
    AUDIO = "audio"

class NamingManager:
    """统一的文件命名和路径管理器"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.current_session = None
        
    def create_recording_session(self, custom_timestamp: str = None, mode_override: str = None) -> Dict[str, Any]:
        """
        创建新的录制会话，返回会话信息
        
        Args:
            custom_timestamp: 自定义时间戳，如果为None则自动生成
            mode_override: 模式覆盖，如果为None则使用配置文件中的模式
            
        Returns:
            Dict: 包含会话目录路径和元数据的字典
        """
        # 生成时间戳
        if custom_timestamp:
            timestamp = custom_timestamp
        else:
            timestamp_format = self.config_manager.get_timestamp_format()
            timestamp = time.strftime(timestamp_format, time.localtime())
        
        # 确定录制模式
        if mode_override:
            current_mode = mode_override
        else:
            current_mode = self.config_manager.get_recording_config()["mode"]
        
        # 创建会话目录
        session_paths = self.config_manager.create_session_directory(timestamp, current_mode)
        
        self.current_session = {
            "timestamp": timestamp,
            "paths": session_paths,
            "files_created": []
        }
        
        logger.info(f"创建录制会话: {self.current_session['paths']['session_dir']}")
        return self.current_session
    
    def get_kinect_output_paths(self, cmd_type_str: str) -> Dict[str, str]:
        """
        获取Kinect输出路径配置
        
        Args:
            cmd_type_str: 命令类型字符串 ("master", "subordinate", "standalone")
            
        Returns:
            Dict: 输出路径配置
        """
        if not self.current_session:
            raise RuntimeError("必须先创建录制会话")
            
        session_dir = self.current_session["paths"]["session_dir"]
        
        if cmd_type_str == "standalone":
            return {"standalone": session_dir}
        else:
            # sync模式下所有设备都输出到同一个会话目录
            return {"sync": session_dir}
    
    def generate_kinect_filename(self, cmd_type_str: str, ip: str, device_index: int) -> str:
        """
        生成Kinect录制文件名
        
        Args:
            cmd_type_str: 命令类型 ("master", "subordinate", "standalone")
            ip: 设备IP地址
            device_index: 设备索引
            
        Returns:
            str: 生成的文件名
        """
        if not self.current_session:
            raise RuntimeError("必须先创建录制会话")
            
        timestamp = self.current_session["timestamp"]
        device_name = self.config_manager.get_device_name("kinect", ip, device_index)
        
        # 根据命令类型添加前缀
        if cmd_type_str == "master":
            prefix = "master"
        elif cmd_type_str == "subordinate":  
            prefix = "sub"
        else:  # standalone
            prefix = "standalone"
            
        filename = f"{timestamp}-{prefix}-{device_name}.mkv"
        
        # 记录创建的文件
        self.current_session["files_created"].append(filename)
        
        return filename
    
    def generate_audio_filename(self, device_index: int) -> str:
        """
        生成音频录制文件名
        
        Args:
            device_index: 音频设备索引
            
        Returns:
            str: 生成的文件名
        """
        if not self.current_session:
            raise RuntimeError("必须先创建录制会话")
            
        timestamp = self.current_session["timestamp"]
        device_name = self.config_manager.get_device_name("audio", "local", device_index)
        
        filename = f"{timestamp}-{device_name}.wav"
        
        # 记录创建的文件
        self.current_session["files_created"].append(filename)
        
        return filename
    
    def get_audio_output_path(self) -> str:
        """
        获取音频输出路径
        
        Returns:
            str: 音频输出路径
        """
        if not self.current_session:
            raise RuntimeError("必须先创建录制会话")
            
        return self.current_session["paths"]["session_dir"]
    
    def finalize_session(self, **metadata) -> None:
        """
        完成录制会话，保存会话信息
        
        Args:
            **metadata: 额外的会话元数据
        """
        if not self.current_session:
            logger.warning("没有活动的录制会话需要完成")
            return
            
        session_dir = self.current_session["paths"]["session_dir"]
        timestamp = self.current_session["timestamp"]
        
        # 添加文件列表到元数据
        session_metadata = {
            "files_created": self.current_session["files_created"],
            "total_files": len(self.current_session["files_created"]),
            **metadata
        }
        
        # 创建会话信息文件
        self.config_manager.create_session_info(
            session_dir, 
            timestamp, 
            **session_metadata
        )
        
        logger.info(f"录制会话已完成，共创建 {len(self.current_session['files_created'])} 个文件")
        self.current_session = None
    
    def get_current_session_info(self) -> Dict[str, Any]:
        """获取当前会话信息"""
        return self.current_session.copy() if self.current_session else None
    
    def cleanup_failed_session(self) -> None:
        """清理失败的会话"""
        if self.current_session:
            logger.warning("清理未完成的录制会话")
            self.current_session = None

    @staticmethod
    def ensure_directory(path: str) -> None:
        """确保目录存在"""
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            logger.debug(f"创建目录: {path}")
