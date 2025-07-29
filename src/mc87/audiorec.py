import time
import wave
import json
import threading
from datetime import datetime
import os
from typing import Dict,List

import pyaudio
import colorama
from colorama import Fore, Style

colorama.init()
default_config = {
    "format":8, # 8,4,2 --> 质量逐渐升高
    "channels":1, #通道数量
    "rate":44100, #每秒录制的样本数量
    "is_input":True, #是否是输入设备
    "input_device_index":[3], #输入设备
    "frames_per_buffer":1024, #每帧的样本数
    "mode": "timing", # timing(定时) 和 manual(自动)
    "timing": 5,
    "outpath": "./"
}

class AudioRecorder:
    def __init__(self,config:Dict=default_config):
        self.config = config
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
    
    def show_devices(self,filter=True) -> None:
        device_count = self.audio.get_device_count()
        for i in range(device_count):
            info_dict = self.audio.get_device_info_by_index(i)
            if filter:
                if info_dict.get("maxInputChannels",0) > 0:
                    print(format_device_info(info_dict))
            else:
                print(format_device_info(info_dict))
    
    def show_default_device(self) -> None:
        device_default:Dict = self.audio.get_default_input_device_info()
        print(format_device_info(device_default,tip="默认设备"))
        
    def show_config(self,indent:int=2) -> None:
        print(f'{Fore.RED}{json.dumps(self.config,indent=indent)}{Style.RESET_ALL}')

    def get_config(self) -> Dict:
        return self.config
    
    def set_config(self,config:Dict) -> None:
        self.config = config
    
    def record_multi_devices(self) -> None:
        if self.is_recording:
            return

        if not self.config.get("input_device_index"):
            print(f"{Fore.RED}✘ 错误: 没有指定输入设备{Style.RESET_ALL}")
            return
        
        self.is_recording = True
        self.recording_lock = threading.Lock()
        self.stop_recording = threading.Event()
        self.recording_threads:List[threading.Thread] = []
        self.audio_data = {}
        
        # 新增：线程同步相关
        device_count = len(self.config.get("input_device_index", []))
        self.ready_barrier = threading.Barrier(device_count + 1)  # +1 for main thread
        self.actual_start_time = None
        self.actual_end_time = None
        
        try:
            for idx in self.config.get("input_device_index",[]):
                thread = threading.Thread(
                    target=self._record_single_device,
                    args=(idx,),
                    daemon=True
                )
                thread.start()
                self.recording_threads.append(thread)
            
            print(f"{Fore.YELLOW}⏳ 等待所有设备准备就绪(数量:{len(self.config.get('input_device_index',[]))})...{Style.RESET_ALL}")
            
            # 等待所有录音线程准备完毕
            self.ready_barrier.wait()
            
            # 记录实际开始时间
            self.actual_start_time = time.time()
            print(f"{Fore.GREEN}🎙️  所有设备已准备就绪，开始录音！{Style.RESET_ALL}")
            
            if self.config.get("mode","") == "timing":
                print(f'{Fore.YELLOW}⏰ 定时录音模式: {self.config.get("timing", 5)} 秒{Style.RESET_ALL}')
                timing = self.config.get("timing", 5)
                #动态刷新
                for i in range(timing, 0, -1):
                    print(f"\r{Fore.YELLOW} 剩余时间: {i} 秒{Style.RESET_ALL}", end="", flush=True)
                    time.sleep(1)
                print() 
                self.stop_recording.set()
            else:
                print(f"{Fore.YELLOW} ▶ 手动录音模式 - 按回车键停止{Style.RESET_ALL}")
                input()
                self.stop_recording.set()
            
            # 记录实际结束时间
            self.actual_end_time = time.time()
            
            # 等待所有线程结束
            for thread in self.recording_threads:
                thread.join()
            
            # 计算实际录音时长
            actual_duration = self.actual_end_time - self.actual_start_time if self.actual_start_time else 0
            
            self._save_audio_files()
            print(f"{Fore.GREEN}✔ 录音完成{Style.RESET_ALL}")
            print(f"{Fore.CYAN} 实际录音时长: {actual_duration:.2f} 秒{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.RED}✘ 录音失败: {str(e)}{Style.RESET_ALL}")
            self.stop_recording.set()
        finally:
            self.is_recording = False
            self._cleanup()
        
    def _record_single_device(self, device_idx: int):
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
                        
            # 等待所有设备都准备好
            self.ready_barrier.wait()            
            while not self.stop_recording.is_set():
                try:
                    data = stream.read(self.config["frames_per_buffer"], exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    print(f'{Fore.RED}-- 设备{device_idx} 读取数据失败: {e}{Style.RESET_ALL}')
                    break
            
            # 线程安全地存储数据
            with self.recording_lock:
                self.audio_data[device_idx] = frames
        
            print(f"{Fore.LIGHTRED_EX}● 设备 {device_idx} 录音结束{Style.RESET_ALL}")
            
        except Exception as e:
            print(f'{Fore.RED}✘ 设备{device_idx} 初始化失败: {e}{Style.RESET_ALL}')
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
                    name, ext = os.path.splitext(filename_template)
                    filename = f"{name}_d{device_idx}{ext}"
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
                
                print(f"{Fore.GREEN}✔ 设备 {device_idx} 录音已保存: {file_path} ({file_size_mb:.2f}MB){Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}✘ 设备 {device_idx} 保存失败: {str(e)}{Style.RESET_ALL}")

    def _cleanup(self):
        if hasattr(self, 'recording_threads'):
            self.recording_threads.clear()
        if hasattr(self, 'audio_data'):
            self.audio_data.clear()
        if hasattr(self, 'ready_barrier'):
            del self.ready_barrier
            
    def close_audio(self) -> None:
        self.audio.terminate()

def format_device_info(device_info, indent=2, tip:str="设备") -> str:
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
    low_input_latency = device_info.get("defaultLowInputLatency", 0)
    high_input_latency = device_info.get("defaultHighInputLatency", 0)
    low_output_latency = device_info.get("defaultLowOutputLatency", 0)
    high_output_latency = device_info.get("defaultHighOutputLatency", 0)
    
    indent_str = " " * indent
    formatted_info = (
        f"{Fore.CYAN}{tip}{Fore.RED}{index}:{Style.RESET_ALL}\n"
        f"{indent_str}{Fore.GREEN}设备编号:{Style.RESET_ALL} {index}\n"
        f"{indent_str}{Fore.GREEN}设备名称:{Style.RESET_ALL} {name}\n"
        f"{indent_str}{Fore.GREEN}音频接口类型:{Style.RESET_ALL} {host_api}\n"
        f"{indent_str}{Fore.GREEN}最大输入声道数:{Style.RESET_ALL} {max_input_channels} (支持 {max_input_channels} 个麦克风)\n"
        f"{indent_str}{Fore.GREEN}最大输出声道数:{Style.RESET_ALL} {max_output_channels} (支持 {max_output_channels} 个扬声器)\n"
        f"{indent_str}{Fore.GREEN}默认采样率:{Style.RESET_ALL} {default_sample_rate:.0f} Hz\n"
        f"{indent_str}{Fore.GREEN}最小输入延迟:{Style.RESET_ALL} {low_input_latency:.3f} 秒\n"
        f"{indent_str}{Fore.GREEN}最大输入延迟:{Style.RESET_ALL} {high_input_latency:.3f} 秒\n"
        f"{indent_str}{Fore.GREEN}最小输出延迟:{Style.RESET_ALL} {low_output_latency:.3f} 秒\n"
        f"{indent_str}{Fore.GREEN}最大输出延迟:{Style.RESET_ALL} {high_output_latency:.3f} 秒"
    )
    return formatted_info


if __name__ == '__main__':
    recorder = AudioRecorder()
    recorder.show_devices()
    # recorder.record_multi_devices()