import time
import wave
import json
import threading
from datetime import datetime
import os
from typing import Dict,List
import logging

import pyaudio

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 默认配置（仅作为后备配置，不建议直接使用）
_default_config = {
    "format": 8, # 8,4,2 --> 质量逐渐升高
    "channels": 1, #通道数量
    "rate": 44100, #每秒录制的样本数量
    "is_input": True, #是否是输入设备
    "input_device_index": [1], #输入设备
    "frames_per_buffer": 1024, #每帧的样本数
    "mode": "timing", # timing(定时) 和 manual(自动)
    "timing": 5,
    "outpath": "./"
}

class AudioRecorder:
    def __init__(self, config: Dict = None):
        """
        初始化音频录制器
        :param config: 配置字典，如果为None则使用默认配置
        """
        if config is None:
            config = _default_config.copy()
        
        self.config = config
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
    
    def show_devices(self, filter=True) -> None:
        """显示可用音频设备"""
        device_count = self.audio.get_device_count()
        logger.info(f"发现 {device_count} 个音频设备")
        
        for i in range(device_count):
            info_dict = self.audio.get_device_info_by_index(i)
            if filter:
                if info_dict.get("maxInputChannels", 0) > 0:
                    print(format_device_info(info_dict))
            else:
                print(format_device_info(info_dict))
    
    def show_default_device(self) -> None:
        """显示默认音频设备"""
        device_default: Dict = self.audio.get_default_input_device_info()
        print(format_device_info(device_default, tip="默认设备"))
        
    def show_config(self, indent: int = 2) -> None:
        """显示当前配置"""
        logger.info("当前音频录制配置:")
        logger.info(f"{json.dumps(self.config, indent=indent)}")

    def get_config(self) -> Dict:
        return self.config
    
    def set_config(self, config: Dict) -> None:
        self.config = config
        logger.debug("音频录制配置已更新")
    
    def record_multi_devices(self) -> None:
        """录制多设备音频"""
        if self.is_recording:
            logger.warning("录制已在进行中，忽略新的录制请求")
            return

        if not self.config.get("input_device_index"):
            logger.error("没有指定输入设备")
            return
        
        device_indices = self.config.get("input_device_index", [])
        logger.info(f"开始多设备录制，设备数量: {len(device_indices)}")
        logger.debug(f"使用设备索引: {device_indices}")
        
        self.is_recording = True
        self.recording_lock = threading.Lock()
        self.stop_recording = threading.Event()
        self.recording_threads: List[threading.Thread] = []
        self.audio_data = {}
        
        # 线程同步相关
        device_count = len(device_indices)
        self.ready_barrier = threading.Barrier(device_count + 1)  # +1 for main thread
        self.actual_start_time = None
        self.actual_end_time = None
        
        try:
            for idx in device_indices:
                thread = threading.Thread(
                    target=self._record_single_device,
                    args=(idx,),
                    daemon=True
                )
                thread.start()
                self.recording_threads.append(thread)
            
            logger.info(f"等待 {device_count} 个设备准备就绪...")
            
            # 等待所有录音线程准备完毕
            self.ready_barrier.wait()
            
            # 记录实际开始时间
            self.actual_start_time = time.time()
            logger.info("所有设备已准备就绪，开始录音")
            
            if self.config.get("mode", "") == "timing":
                timing = self.config.get("timing", 5)
                logger.info(f"定时录音模式: {timing} 秒")
                
                # 简化的倒计时显示
                for i in range(timing, 0, -1):
                    if i <= 3:  # 只在最后3秒显示倒计时
                        logger.debug(f"剩余时间: {i} 秒")
                    time.sleep(1)
                    
                self.stop_recording.set()
            else:
                logger.info("手动录音模式 - 等待停止信号")
                input("按回车键停止录音...")
                self.stop_recording.set()
            
            # 记录实际结束时间
            self.actual_end_time = time.time()
            
            # 等待所有线程结束
            for thread in self.recording_threads:
                thread.join()
            
            # 计算实际录音时长
            actual_duration = self.actual_end_time - self.actual_start_time if self.actual_start_time else 0
            
            self._save_audio_files()
            logger.info(f"录音完成，实际时长: {actual_duration:.2f} 秒")
                
        except Exception as e:
            logger.error(f"录音失败: {str(e)}")
            self.stop_recording.set()
        finally:
            self.is_recording = False
            self._cleanup()
        
    def _record_single_device(self, device_idx: int):
        """单个设备录制任务"""
        frames = []
        stream = None
        
        try:
            # 初始化音频流
            stream = self.audio.open(
                format=self.config["format"],
                channels=self.config["channels"],
                rate=self.config["rate"],
                input=True,
                input_device_index=device_idx,
                frames_per_buffer=self.config["frames_per_buffer"]
            )
            
            logger.debug(f"设备 {device_idx} 音频流初始化完成")
            
            # 等待所有设备都准备好
            self.ready_barrier.wait()
            
            while not self.stop_recording.is_set():
                try:
                    data = stream.read(self.config["frames_per_buffer"], exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    logger.error(f"设备 {device_idx} 读取数据失败: {e}")
                    break
            
            # 线程安全地存储数据
            with self.recording_lock:
                self.audio_data[device_idx] = frames
        
            logger.info(f"设备 {device_idx} 录音结束")
            
        except Exception as e:
            logger.error(f"设备 {device_idx} 初始化失败: {e}")
            # 即使失败也要参与barrier，防止死锁
            try:
                self.ready_barrier.wait()
            except threading.BrokenBarrierError:
                pass
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
                
    def _save_audio_files(self):
        outpath = self.config.get("outpath","./")
        os.makedirs(outpath,exist_ok=True)
        
        filename_template = self.config.get("filename")

        for device_idx,frames in self.audio_data.items():
            if not frames:
                continue
            
            if filename_template:
                # 如果有多个设备，则在文件名中附加设备索引以保持唯一性
                if len(self.config.get("input_device_index", [])) > 1:
                    # 使用设备命名或索引生成唯一文件名
                    name, ext = os.path.splitext(filename_template)
                    # 尝试从配置中获取设备名称
                    device_names = self.config.get("device_names", {})
                    device_name = device_names.get(str(device_idx), f"d{device_idx}")
                    filename = f"{name}_{device_name}{ext}"
                else:
                    filename = filename_template
            else:
                # 如果配置中未提供“filename”，则回退到旧的命名方案
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f'd{device_idx}_{timestamp}.wav'

            # 用户要求mp3，但wave库保存wav文件。
            if filename.lower().endswith('.mp3'):
                filename = os.path.splitext(filename)[0] + '.wav'

            file_path = os.path.join(outpath,filename)
            
            try:
                with wave.open(file_path,"wb") as wf:
                    wf.setnchannels(self.config["channels"])
                    wf.setsampwidth(self.audio.get_sample_size(self.config["format"]))
                    wf.setframerate(self.config["rate"])
                    wf.writeframes(b''.join(frames))
                
                # 计算文件大小
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)
                
                logger.debug(f"设备 {device_idx} 录音已保存: {os.path.basename(file_path)} ({file_size_mb:.2f}MB)")
            except Exception as e:
                logger.error(f"设备 {device_idx} 保存失败: {str(e)}")

    def _cleanup(self):
        """清理录制资源"""
        if hasattr(self, 'recording_threads'):
            self.recording_threads.clear()
        if hasattr(self, 'audio_data'):
            self.audio_data.clear()
        if hasattr(self, 'ready_barrier'):
            del self.ready_barrier
        logger.debug("音频录制资源已清理")
            
    def close_audio(self) -> None:
        """关闭音频系统"""
        self.audio.terminate()
        logger.debug("音频系统已关闭")

def format_device_info(device_info, indent=2, tip: str = "设备") -> str:
    """格式化设备信息显示"""
    # 映射主机 API 索引到直观名称
    host_api_map = {
        0: "Windows DirectSound",
        1: "MME", 
        2: "ASIO",
        3: "WASAPI",
        4: "WDM-KS",
    }
    
    index = device_info.get("index", "未知")
    name = device_info.get("name", "未知设备")
    host_api = host_api_map.get(device_info.get("hostApi", -1), "未知接口")
    max_input_channels = device_info.get("maxInputChannels", 0)
    max_output_channels = device_info.get("maxOutputChannels", 0)
    default_sample_rate = device_info.get("defaultSampleRate", 0)
    
    indent_str = " " * indent
    formatted_info = (
        f"{tip} {index}:\n"
        f"{indent_str}名称: {name}\n"
        f"{indent_str}接口: {host_api}\n"
        f"{indent_str}输入声道: {max_input_channels}\n"
        f"{indent_str}输出声道: {max_output_channels}\n"
        f"{indent_str}采样率: {default_sample_rate:.0f} Hz"
    )
    return formatted_info


if __name__ == '__main__':
    # 设置日志级别为DEBUG以显示详细信息
    logging.getLogger().setLevel(logging.DEBUG)
    
    recorder = AudioRecorder()  # 使用默认配置
    # logger.info("=== 音频设备列表 ===")
    # recorder.show_devices()
    # logger.info("=== 音频设备列表结束 ===")
    recorder.record_multi_devices()  # 取消注释以测试录制