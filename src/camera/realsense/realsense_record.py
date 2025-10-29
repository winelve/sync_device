"""
RealSense D405 录制模块
提供简化的接口用于录制深度和彩色数据
"""

import pyrealsense2 as rs
import os
import time
from datetime import datetime
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class RealSenseRecorder:
    """RealSense D405 录制器，支持同时录制深度和彩色数据"""
    
    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        output_dir: str = "./recordings",
        enable_depth: bool = True,
        enable_color: bool = True
    ):
        """
        初始化 RealSense 录制器
        
        Args:
            width: 分辨率宽度，默认 640
            height: 分辨率高度，默认 480
            fps: 帧率，默认 30
            output_dir: 输出目录，默认 "./recordings"
            enable_depth: 是否启用深度流，默认 True
            enable_color: 是否启用彩色流，默认 True
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.output_dir = output_dir
        self.enable_depth = enable_depth
        self.enable_color = enable_color
        
        # 内部变量
        self.pipeline: Optional[rs.pipeline] = None
        self.config: Optional[rs.config] = None
        self.recording_path: Optional[str] = None
        self._is_recording = False
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info(f"RealSense 录制器初始化: {width}x{height} @ {fps}fps")
    
    def start_recording(self, duration: Optional[float] = None, filename: Optional[str] = None) -> str:
        """
        开始录制
        
        Args:
            duration: 录制时长（秒），None 表示手动停止
            filename: 输出文件名（不含扩展名），None 则自动生成时间戳文件名
            
        Returns:
            str: 录制文件的完整路径
        """
        if self._is_recording:
            logger.warning("录制已经在进行中")
            return self.recording_path
        
        # 生成文件名
        if filename is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"realsense_{timestamp}"
        
        # 确保文件名以 .bag 结尾
        if not filename.endswith('.bag'):
            filename += '.bag'
        
        self.recording_path = os.path.join(self.output_dir, filename)
        
        # 初始化 pipeline 和 config
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        
        # 配置流
        if self.enable_depth:
            self.config.enable_stream(
                rs.stream.depth,
                self.width,
                self.height,
                rs.format.z16,
                self.fps
            )
            logger.info(f"启用深度流: {self.width}x{self.height} @ {self.fps}fps")
        
        if self.enable_color:
            self.config.enable_stream(
                rs.stream.color,
                self.width,
                self.height,
                rs.format.rgb8,
                self.fps
            )
            logger.info(f"启用彩色流: {self.width}x{self.height} @ {self.fps}fps")
        
        # 启用录制到文件
        self.config.enable_record_to_file(self.recording_path)
        
        # 开始 pipeline
        try:
            self.pipeline.start(self.config)
            self._is_recording = True
            logger.info(f"开始录制: {self.recording_path}")
            
            # 如果指定了时长，则自动停止
            if duration is not None:
                logger.info(f"将录制 {duration} 秒")
                time.sleep(duration)
                self.stop_recording()
            
            return self.recording_path
            
        except Exception as e:
            logger.error(f"启动录制失败: {e}")
            self._cleanup()
            raise
    
    def stop_recording(self):
        """停止录制"""
        if not self._is_recording:
            logger.warning("当前没有进行录制")
            return
        
        try:
            if self.pipeline:
                self.pipeline.stop()
            logger.info(f"录制已停止: {self.recording_path}")
            
        except Exception as e:
            logger.error(f"停止录制时出错: {e}")
        
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """清理资源"""
        self._is_recording = False
        self.pipeline = None
        self.config = None
    
    def is_recording(self) -> bool:
        """检查是否正在录制"""
        return self._is_recording
    
    def get_recording_path(self) -> Optional[str]:
        """获取当前录制文件路径"""
        return self.recording_path if self._is_recording else None
    
    @staticmethod
    def list_devices() -> list:
        """列出所有可用的 RealSense 设备"""
        ctx = rs.context()
        devices = ctx.query_devices()
        device_list = []
        
        for i, device in enumerate(devices):
            device_info = {
                'index': i,
                'name': device.get_info(rs.camera_info.name),
                'serial': device.get_info(rs.camera_info.serial_number),
                'firmware': device.get_info(rs.camera_info.firmware_version)
            }
            device_list.append(device_info)
            logger.info(f"设备 {i}: {device_info['name']} (SN: {device_info['serial']})")
        
        return device_list
    
    @staticmethod
    def get_supported_resolutions(device_index: int = 0) -> dict:
        """
        获取设备支持的分辨率和帧率
        
        Args:
            device_index: 设备索引
            
        Returns:
            dict: {'depth': [(width, height, fps), ...], 'color': [(width, height, fps), ...]}
        """
        ctx = rs.context()
        devices = ctx.query_devices()
        
        if device_index >= len(devices):
            logger.error(f"设备索引 {device_index} 超出范围")
            return {'depth': [], 'color': []}
        
        device = devices[device_index]
        supported = {'depth': set(), 'color': set()}
        
        for sensor in device.query_sensors():
            for profile in sensor.get_stream_profiles():
                if profile.stream_type() == rs.stream.depth:
                    video_profile = profile.as_video_stream_profile()
                    supported['depth'].add((
                        video_profile.width(),
                        video_profile.height(),
                        video_profile.fps()
                    ))
                elif profile.stream_type() == rs.stream.color:
                    video_profile = profile.as_video_stream_profile()
                    supported['color'].add((
                        video_profile.width(),
                        video_profile.height(),
                        video_profile.fps()
                    ))
        
        # 转换为列表并排序
        return {
            'depth': sorted(list(supported['depth'])),
            'color': sorted(list(supported['color']))
        }


# 便捷函数
def quick_record(
    duration: float = 10,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    output_dir: str = "./recordings",
    filename: Optional[str] = None
) -> str:
    """
    快速录制函数（阻塞式）
    
    Args:
        duration: 录制时长（秒）
        width: 分辨率宽度
        height: 分辨率高度
        fps: 帧率
        output_dir: 输出目录
        filename: 输出文件名（可选）
    
    Returns:
        str: 录制文件路径
    """
    recorder = RealSenseRecorder(
        width=width,
        height=height,
        fps=fps,
        output_dir=output_dir
    )
    
    return recorder.start_recording(duration=duration, filename=filename)


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 列出设备
    print("检测 RealSense 设备...")
    devices = RealSenseRecorder.list_devices()
    
    print(devices)
    if not devices:
        print("未检测到 RealSense 设备")
        exit(1)
    
    # 查看支持的分辨率
    print("\n支持的分辨率:")
    resolutions = RealSenseRecorder.get_supported_resolutions(0)
    print("深度流:", resolutions['depth'][:5], "...")  # 只显示前5个
    print("彩色流:", resolutions['color'][:5], "...")
    
    # 方式1: 使用快速录制函数（阻塞式）
    print("\n=== 方式1: 快速录制 ===")
    output_path = quick_record(
        duration=5,
        width=640,
        height=480,
        fps=30,
        output_dir="./recordings/test"
    )
    print(f"录制完成: {output_path}")
    
    # 方式2: 使用录制器对象（可手动控制）
    print("\n=== 方式2: 手动控制录制 ===")
    recorder = RealSenseRecorder(
        width=640,
        height=480,
        fps=30,
        output_dir="./recordings/test"
    )
    
    # 开始录制（不指定时长，需要手动停止）
    recorder.start_recording(filename="manual_test")
    print("录制中...")
    
    # 录制 3 秒
    time.sleep(3)
    
    # 手动停止
    recorder.stop_recording()
    print("录制完成")
