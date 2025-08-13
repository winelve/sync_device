import threading
import time
import os
import logging

from kinect.kinect_record_master import KinectMaster
from mc87.audiorec import AudioRecorder
from config import get_config_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class DeviceCtlSys:
    """
    一个用于同步控制多个设备的系统。
    """
    def __init__(self, config_manager, mode: str = None, is_local_debug: bool = None):
        """
        初始化设备控制系统。
        :param config_manager: 配置管理器实例
        :param mode: 运行模式覆盖, None则使用配置文件中的模式
        :param is_local_debug: 本地调试模式覆盖, None则使用配置文件中的设置
        """
        self.config_manager = config_manager
        
        # 获取配置
        recording_config = config_manager.get_recording_config()
        self.kinect_config = config_manager.get_kinect_config()
        self.audio_config = config_manager.get_audio_config()
        
        # 应用覆盖参数
        self.mode = mode if mode is not None else recording_config["mode"]
        self.is_local_debug = is_local_debug if is_local_debug is not None else recording_config["is_local_debug"]
        self.standalone_delay = recording_config["standalone_delay"]
        self.sync_delay = recording_config["sync_delay"]
        
        # 初始化设备
        self.kinect_master = KinectMaster()
        self.audio_recorder = AudioRecorder(config=self.audio_config)

        self.threads = []
        self.timestamp = ""

    def start_recording(self):
        """根据配置的模式启动录制过程。"""
        logger.info(f"在 {self.mode.upper()} 模式下启动设备控制系统")
        
        self.timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        self._setup_output_paths()

        if self.mode == 'standalone':
            self._start_standalone()
        elif self.mode == 'sync':
            self._start_sync()
        else:
            logger.error(f"未知模式: '{self.mode}'")
            return

        # 等待所有线程完成
        for thread in self.threads:
            thread.join()
            
        logger.info("所有录制进程已完成")

    def _setup_output_paths(self):
        """根据模式和时间戳设置输出路径和文件名。"""
        if self.mode == 'standalone':
            output_dir = os.path.join("output", "standalone", self.timestamp)
            os.makedirs(output_dir, exist_ok=True)
            
            self.kinect_config['output'] = {'standalone': output_dir}
            self.audio_config['outpath'] = output_dir
            self.audio_config['filename'] = f"audio_{self.timestamp}.mp3"
            
            logger.debug(f"独立模式输出目录: {output_dir}")
            
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
            
            logger.debug(f"同步模式输出目录 - Master: {master_dir}, Sub: {sub_dir}, Audio: {audio_dir}")
        
        # 更新录音机实例的配置，因为它是在__init__中用旧配置创建的
        self.audio_recorder.set_config(self.audio_config)

    def _start_standalone(self):
        """处理独立录制工作流。"""
        logger.info("并行启动设备...")

        # Kinect线程
        kinect_thread = threading.Thread(target=self._kinect_standalone_task)
        self.threads.append(kinect_thread)

        # 音频线程
        audio_thread = threading.Thread(target=self._audio_task)
        self.threads.append(audio_thread)

        # 启动所有线程
        kinect_thread.start()
        if self.standalone_delay > 0:
            logger.debug(f"等待 {self.standalone_delay} 秒后启动音频录制")
            time.sleep(self.standalone_delay)
        audio_thread.start()

    def _start_sync(self):
        """处理同步录制工作流。"""
        # 步骤 1: 准备Kinect子设备 (这是一个阻塞调用)
        logger.info("正在准备Kinect同步模式...")
        success = self.kinect_master.prepare_sync(self.kinect_config, is_local=self.is_local_debug, timestamp=self.timestamp)
        
        if not success:
            logger.error("Kinect同步模式准备失败")
            return
        
        # Kinect Master线程
        kinect_thread = threading.Thread(target=self._kinect_sync_master_task)
        self.threads.append(kinect_thread)

        # 音频线程
        audio_thread = threading.Thread(target=self._audio_task)
        self.threads.append(audio_thread)
        
        # 启动线程
        kinect_thread.start()
        if self.sync_delay > 0:
            logger.debug(f"等待 {self.sync_delay} 秒后启动音频录制")
            time.sleep(self.sync_delay)
        audio_thread.start()
        
        logger.info("★★★ 正式开始录制 ★★★")

    def _kinect_standalone_task(self):
        """在独立模式下运行Kinect并等待其完成的任务。"""
        try:
            self.kinect_master.start_standalone(self.kinect_config, self.timestamp)
            self.kinect_master.wait_for_subprocess()
            logger.info("Kinect录制完成")
        except Exception as e:
            logger.error(f"Kinect独立任务出错: {e}")
        finally:
            self.kinect_master._cleanup()

    def _kinect_sync_master_task(self):
        """在同步模式下运行Kinect主设备并等待其完成的任务。"""
        try:
            self.kinect_master.start_sync_master(self.kinect_config)
            self.kinect_master.wait_for_subprocess()
            logger.info("Kinect主设备录制完成")
        except Exception as e:
            logger.error(f"Kinect同步主任务出错: {e}")
        finally:
            self.kinect_master._cleanup()

    def _audio_task(self):
        """运行音频录制器的任务。"""
        try:
            # record_multi_devices方法是阻塞的，并处理其自身的生命周期。
            self.audio_recorder.record_multi_devices()
            logger.info("音频录制完成")
        except Exception as e:
            logger.error(f"音频录制任务出错: {e}")
        finally:
            self.audio_recorder.close_audio()


if __name__ == '__main__':
    # 初始化配置管理器
    config_manager = get_config_manager("./config.json")
    
    # 获取录制配置
    recording_config = config_manager.get_recording_config()
    
    logger.info("=== 设备控制系统启动 ===")
    logger.info(f"录制模式: {recording_config['mode']}")
    logger.info(f"录制时长: {recording_config['duration']} 秒")
    logger.info(f"本地调试模式: {recording_config['is_local_debug']}")

    # --- 系统执行 ---
    try:
        controller = DeviceCtlSys(
            config_manager=config_manager,
            # 可以在这里覆盖配置文件中的设置
            # mode='standalone',  # 取消注释以覆盖配置文件中的模式
            # is_local_debug=False,  # 取消注释以覆盖配置文件中的设置
        )
        controller.start_recording()
    except Exception as e:
        logger.error(f"主控制器发生意外错误: {e}")
    finally:
        logger.info("设备控制系统已关闭")
