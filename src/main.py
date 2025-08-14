import threading
import time
import logging

try:
    from .kinect.kinect_record_master import KinectMaster
    from .mc87.audiorec import AudioRecorder
    from .utils.config import get_config_manager
    from .utils.naming import NamingManager
except ImportError:
    from kinect.kinect_record_master import KinectMaster
    from mc87.audiorec import AudioRecorder
    from utils.config import get_config_manager
    from utils.naming import NamingManager

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
        
        # 初始化命名管理器
        self.naming_manager = NamingManager(config_manager)
        
        # 初始化设备
        self.kinect_master = KinectMaster(naming_manager=self.naming_manager)
        self.audio_recorder = AudioRecorder(config=self.audio_config)

        self.threads = []

    def start_recording(self):
        """根据配置的模式启动录制过程。"""
        logger.info(f"在 {self.mode.upper()} 模式下启动设备控制系统")
        
        # 创建录制会话，传入正确的模式
        session = self.naming_manager.create_recording_session(mode_override=self.mode)
        
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
        
        # 完成录制会话
        self.naming_manager.finalize_session(
            mode=self.mode,
            device_count=self._get_device_count(),
            duration=self.config_manager.get_recording_config()["duration"]
        )
            
        logger.info("所有录制进程已完成")

    def _get_device_count(self) -> int:
        """获取参与录制的设备数量"""
        count = 0
        # Kinect设备数量
        if self.mode == 'standalone':
            count += 1  # 一个kinect设备
        else:  # sync模式
            ip_devices = self.kinect_config.get("--ip-devices", {})
            for devices in ip_devices.values():
                count += len(devices)
        
        # 音频设备数量
        count += len(self.audio_config.get("input_device_index", []))
        
        return count

    def _setup_output_paths(self):
        """根据模式和时间戳设置输出路径和文件名。"""
        session = self.naming_manager.get_current_session_info()
        if not session:
            raise RuntimeError("没有活动的录制会话")
        
        timestamp = session["timestamp"]
        session_dir = session["paths"]["session_dir"]
        
        # 更新Kinect配置
        if self.mode == 'standalone':
            self.kinect_config['output'] = {'standalone': session_dir}
        elif self.mode == 'sync':
            self.kinect_config['output'] = {'sync': session_dir}
        
        # 更新音频配置
        self.audio_config['outpath'] = session_dir
        
        # 为每个音频设备生成文件名
        input_devices = self.audio_config.get("input_device_index", [])
        if len(input_devices) == 1:
            # 单个设备，使用简单的文件名
            filename = self.naming_manager.generate_audio_filename(input_devices[0])
            self.audio_config['filename'] = filename
        else:
            # 多个设备，将在音频录制器内部处理命名
            self.audio_config['filename'] = f"{timestamp}-audio.wav"  # 模板名称
        
        logger.debug(f"录制会话目录: {session_dir}")
        
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
        session = self.naming_manager.get_current_session_info()
        timestamp = session["timestamp"] if session else None
        success = self.kinect_master.prepare_sync(self.kinect_config, is_local=self.is_local_debug, timestamp=timestamp)
        
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
            session = self.naming_manager.get_current_session_info()
            timestamp = session["timestamp"] if session else None
            self.kinect_master.start_standalone(self.kinect_config, timestamp)
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
            # mode='sync',  # 取消注释以覆盖配置文件中的模式
            # is_local_debug=False,  # 取消注释以覆盖配置文件中的设置
        )
        controller.start_recording()
    except Exception as e:
        logger.error(f"主控制器发生意外错误: {e}")
    finally:
        logger.info("设备控制系统已关闭")
