import threading
import time
import os

from kinect.kinect_record_master import KinectMaster
from mc87.audiorec import AudioRecorder, default_config as default_audio_config
from colorama import Fore, Style

standalone_delay = 0
sync_delay = 0

class DeviceCtlSys:
    """
    一个用于同步控制多个设备的系统。
    """
    def __init__(self, kinect_config: dict, audio_config: dict, mode: str = 'standalone', is_local_debug: bool = True):
        """
        初始化设备控制系统。
        :param kinect_config: Kinect的配置字典。
        :param audio_config: AudioRecorder的配置字典。
        :param mode: 运行模式, 'standalone' 或 'sync'。
        :param is_local_debug: 对于Kinect同步模式，如果为True，则扫描本地网络。
        """
        self.kinect_master = KinectMaster()
        self.audio_recorder = AudioRecorder(config=audio_config)
        
        self.kinect_config = kinect_config
        self.audio_config = audio_config
        self.mode = mode
        self.is_local_debug = is_local_debug

        self.threads = []
        self.timestamp = ""

    def start_recording(self):
        """根据配置的模式启动录制过程。"""
        print(f"--- 在 {self.mode.upper()} 模式下启动设备控制系统 ---")
        
        self.timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        self._setup_output_paths()

        if self.mode == 'standalone':
            self._start_standalone()
        elif self.mode == 'sync':
            self._start_sync()
        else:
            print(f"错误: 未知模式 '{self.mode}'")
            return

        # 等待所有线程完成
        for thread in self.threads:
            thread.join()
            
        print("--- 所有录制进程已完成。 ---")

    def _setup_output_paths(self):
        """根据模式和时间戳设置输出路径和文件名。"""
        if self.mode == 'standalone':
            output_dir = os.path.join("output", "standalone", self.timestamp)
            os.makedirs(output_dir, exist_ok=True)
            
            self.kinect_config['output'] = {'standalone': output_dir}
            self.audio_config['outpath'] = output_dir
            self.audio_config['filename'] = f"audio_{self.timestamp}.mp3"
            
        elif self.mode == 'sync':
            base_output_dir = "output/sync"
            master_dir = os.path.join(base_output_dir, 'master')
            sub_dir = os.path.join(base_output_dir, 'sub')
            audio_dir = os.path.join(base_output_dir, 'audio')
            
            os.makedirs(master_dir, exist_ok=True)
            os.makedirs(sub_dir, exist_ok=True)
            os.makedirs(audio_dir, exist_ok=True)
            
            self.kinect_config['output'] = {'master': master_dir, 'sub': sub_dir}
            self.audio_config['outpath'] = audio_dir
            self.audio_config['filename'] = f"audio_{self.timestamp}.mp3"
        
        # 更新录音机实例的配置，因为它是在__init__中用旧配置创建的
        self.audio_recorder.set_config(self.audio_config)

    def _start_standalone(self):
        """处理独立录制工作流。"""
        print("并行启动设备...")

        # Kinect线程
        kinect_thread = threading.Thread(target=self._kinect_standalone_task)
        self.threads.append(kinect_thread)

        # 音频线程
        audio_thread = threading.Thread(target=self._audio_task)
        self.threads.append(audio_thread)

        # 启动所有线程
        kinect_thread.start()
        time.sleep(standalone_delay)
        audio_thread.start()

    def _start_sync(self):
        """处理同步录制工作流。"""
        # 步骤 1: 准备Kinect子设备 (这是一个阻塞调用)
        print("正在准备Kinect同步模式... 这可能需要一些时间。")
        self.kinect_master.prepare_sync(self.kinect_config, is_local=self.is_local_debug, timestamp=self.timestamp)

        
        # Kinect Master线程
        kinect_thread = threading.Thread(target=self._kinect_sync_master_task)
        self.threads.append(kinect_thread)

        # 音频线程
        audio_thread = threading.Thread(target=self._audio_task)
        self.threads.append(audio_thread)
        
        # 启动线程
        kinect_thread.start()
        time.sleep(sync_delay)
        audio_thread.start()
        print(f"{Fore.RED}{Style.BRIGHT}") # Set text to bright red
        print("========================================")
        print("         ★★★ 正式开始录制 ★★★         ") # Added more stars for emphasis
        print("========================================")
        print(Style.RESET_ALL) # Reset all styles and colors

    def _kinect_standalone_task(self):
        """在独立模式下运行Kinect并等待其完成的任务。"""
        try:
            self.kinect_master.start_standalone(self.kinect_config, self.timestamp)
            self.kinect_master.wait_for_subprocess()
            print("Kinect录制完成。")
        except Exception as e:
            print(f"Kinect独立任务出错: {e}")
        finally:
            self.kinect_master._cleanup()

    def _kinect_sync_master_task(self):
        """在同步模式下运行Kinect主设备并等待其完成的任务。"""
        try:
            self.kinect_master.start_sync_master(self.kinect_config)
            self.kinect_master.wait_for_subprocess()
            print("Kinect主设备录制完成。")
        except Exception as e:
            print(f"Kinect同步主任务出错: {e}")
        finally:
            self.kinect_master._cleanup()

    def _audio_task(self):
        """运行音频录制器的任务。"""
        try:
            # record_multi_devices方法是阻塞的，并处理其自身的生命周期。
            self.audio_recorder.record_multi_devices()
            print("音频录制完成.")
        except Exception as e:
            print(f"音频录制任务出错: {e}")
        finally:
            self.audio_recorder.close_audio()


if __name__ == '__main__':
    # --- 配置 ---
    RECORDING_MODE = 'sync'  # 'standalone' 或 'sync'
    RECORDING_SECONDS = 10

    # Kinect配置
    kinect_cmd_d = {
        "--device" : 1,
        "-l" : RECORDING_SECONDS,
        "-c" : "720p",
        "-r": 15,
        "--imu": "OFF",
        "--sync-delay": 200,
        "-e": 1,
        "--ip-devices": {
            "127.0.0.1": [0,2,3] # 对于同步模式，将IP映射到设备索引
        },
        "output": {}  # 将由DeviceCtlSys动态设置
    }

    # 音频录制器配置
    # 注意: 您可能需要先运行audiorec.py来查看可用的设备索引。
    audio_rec_config = default_audio_config.copy()
    audio_rec_config.update({
        "input_device_index": [6], # 重要: 请将其更改为您的麦克风索引
        "mode": "timing",
        "timing": RECORDING_SECONDS,
        "outpath": "" # 将由DeviceCtlSys动态设置
    })
    
    standalone_delay = 0
    sync_delay = 0.86

    # --- 系统执行 ---
    try:
        controller = DeviceCtlSys(
            kinect_config=kinect_cmd_d,
            audio_config=audio_rec_config,
            mode=RECORDING_MODE,
            is_local_debug=True # 如果您有远程设备网络，请设置为False
        )
        controller.start_recording()
    except Exception as e:
        print(f"主控制器发生意外错误: {e}")
    finally:
        print("\n设备控制系统已关闭。")
