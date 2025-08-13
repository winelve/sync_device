from xmlrpc.client import ServerProxy
import signal
from typing import List,Dict, Tuple
import time
import threading
import subprocess
from enum import Enum
import atexit
import os
import logging

try:
    from .scan_rpc import find_rpc_servers  # 作为模块被导入时
except ImportError:
    from scan_rpc import find_rpc_servers   # 直接运行时

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 全局变量 || 配置参数
# devices_ip = scan_network_fast(is_local=True) #扫描网段下的设备
port = 8000
tool = "./src/kinect/tool/k4arecorder"
done_msg = "[subordinate mode] Waiting for signal from master" # 子设备初始化完成的标志
datetime = ""
config_list = ["--device", "-l", "-c", "-d", "--depth-delay", "-r", "--imu", "--external-sync", "--sync-delay", "-e", "--ip-devices", "output"]

CMD_DICT = {
    "--device" : None,
    "-l" : None,    # record length
    "-c" : None,    # color-mode(分辨率)
    "-d" : None,    # depth-mode(深度相机的模式)
    "--depth-delay": None,  # depth-delay
    "-r": None,    # rate
    "--imu": None, # imu
    "--external-sync": None,  # 同步的类型
    "--sync-delay": None, # 同步延迟
    "-e": None, # 曝光度
    "--ip-devices": None, #给出指定ip的设备
    "output": './', #输出路径
}

class CmdType(Enum):
    Standalone = 0
    Master = 1
    Sub = 2

def parse_cmd(cmd_dict: Dict, cmd_type: CmdType, ip: str = '') -> List[List[str]]:
    """
    解析命令并生成设备指令列表。
    
    首先尝试使用指定的 IP 从 --ip-devices 中获取设备列表。
    如果失败，则回退到使用 --device 的值。
    
    Returns:
        List[List[str]]: 包含所有命令的二维列表。
    """
    cmd_dict = cmd_dict.copy()
    
    device_list = []
    
    # 1. 尝试使用 ip 参数从 --ip-devices 中获取设备列表
    if ip and cmd_dict.get("--ip-devices", {}).get(ip):
        device_list = cmd_dict["--ip-devices"][ip]
    # 2. 如果 --ip-devices 不存在或 ip 不匹配，则回退到使用 --device 的值
    elif cmd_dict.get("--device") is not None:
        device_list = [cmd_dict["--device"]]
    else:
        # 如果既没有 --ip-devices 也没有 --device，则返回空列表
        return []
    
    # 准备基础命令包（排除设备相关参数）
    base_cmdpack = [[k, v] for k, v in cmd_dict.items() 
                    if (v is not None) and (k != "--ip-devices") and 
                       (k != "output") and (k != "--device") and (k in config_list)]
    
    output_config = cmd_dict.get("output", './')
    result_commands = []
    global datetime
    
    # 为每个设备生成命令
    for device_id in device_list:
        cmdList = [tool]
        cmdList.extend(["--device", str(device_id)])
        
        # 根据命令类型配置
        if cmd_type == CmdType.Master:
            output_dir = output_config.get('master', '.') if isinstance(output_config, dict) else '.'
            output_file = f'{output_dir}/master-{datetime}-device{device_id}.mkv'
            cmdList.extend(["--external-sync", "master"])
            
            # 添加其他参数（Master模式跳过sync-delay）
            for pack in base_cmdpack:
                if pack[0] == "--sync-delay":
                    continue
                cmdList.extend([pack[0], str(pack[1])])
                
        elif cmd_type == CmdType.Sub:
            output_dir = output_config.get('sub', '.') if isinstance(output_config, dict) else '.'
            output_file = f'{output_dir}/sub{device_id}-{datetime}-device{device_id}.mkv'
            cmdList.extend(["--external-sync", "subordinate"])
            # 添加其他参数
            for pack in base_cmdpack:
                cmdList.extend([pack[0], str(pack[1])])
                
        elif cmd_type == CmdType.Standalone:
            output_dir = output_config.get('standalone', '.') if isinstance(output_config, dict) else '.'
            output_file = f'{output_dir}/standalone-{datetime}-device{device_id}.mkv'
            # 添加其他参数（Standalone模式跳过sync相关参数）
            for pack in base_cmdpack:
                if pack[0] in ["--sync-delay", "--external-sync"]:
                    continue
                cmdList.extend([pack[0], str(pack[1])])
        
        else:
            continue
        
        cmdList.append(output_file) # 添加输出文件
        # 将命令添加到结果列表
        result_commands.append(cmdList)
    return result_commands


def update_global_datetime(timestamp:str=None):
    global datetime
    if timestamp is None:
        datetime = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    else:
        datetime = timestamp

class KinectMaster:
    def __init__(self):
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        #master进程
        self.process = None
        self.done_count = 0
        # 连接worker
        self.workers = []
        self.devices_ip = []
        
        # 启动输出监听线程
        self.running = False
        self.output_thread = threading.Thread(target=self._monitor_outputs, daemon=True)
    
    def start_standalone(self, cmdDict: Dict, timestamp:str=None):
        """启动独立模式录制"""
        update_global_datetime(timestamp)
        logger.info("启动独立模式录制")
        self._print_cmd_info(cmdDict, is_sync=False)
        
        try:
            # 启动子进程
            cmd_list = parse_cmd(cmdDict, CmdType.Standalone)[0]
            logger.debug(f"执行命令: {' '.join(cmd_list)}")
            
            self.process = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            logger.info("独立模式录制已成功启动")
        except Exception as e:
            logger.error(f"启动独立模式录制失败: {e}")
            raise

    def prepare_sync(self, cmdDict: Dict, is_local: bool = True, timestamp:str=None):
        """准备同步模式：扫描并启动所有子设备"""
        logger.info("开始准备同步模式")
        update_global_datetime(timestamp)
        self._scan_devices(is_local)  # 扫描设备
        
        if not self.devices_ip:
            logger.error("未发现任何可用的同步设备，请检查网络连接或设备状态,同步模式初始化失败，流程已终止")
            return False
            
        logger.info(f"成功扫描到 {len(self.devices_ip)} 个设备: {self.devices_ip}")
        self._print_cmd_info(cmdDict, is_sync=True)
        
        try:
            # 启动子进程
            self._start_sub(cmdDict)
            # 启动监听线程
            self.running = True
            if not self.output_thread.is_alive():
                self.output_thread.start()
                logger.debug("输出监听线程已启动")

            # 确保设备全部初始化
            self._waiting_for_device_init(cmdDict)
            logger.info("同步模式准备完成")
            return True
        except Exception as e:
            logger.error(f"准备同步模式失败: {e}")
            return False

    def start_sync_master(self, cmd_dict: Dict):
        """启动master线程"""
        try:
            cmd_list = parse_cmd(cmd_dict, CmdType.Master)[0]
            logger.info("正在启动master设备")
            logger.debug(f"master运行命令: {' '.join(cmd_list)}")
            
            self.process = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            logger.info("master设备启动成功")
        except Exception as e:
            logger.error(f"启动master设备失败: {e}")
            raise
        
    def wait_for_subprocess(self):
        """等待子进程完成"""
        logger.info("等待录制进程完成...")
        while True:
            if self.process and self.process.poll() is not None:
                logger.info("录制进程已完成")
                break
            time.sleep(1)
    
    def stop_monitoring(self):
        """停止输出监听"""
        self.running = False
        if self.output_thread.is_alive():
            self.output_thread.join()
            logger.debug("输出监听线程已停止")
            
    def _scan_devices(self, is_local: bool):  
        """扫描并连接到worker设备"""
        logger.info(f"开始扫描设备 (本地模式: {is_local})")
        self.devices_ip = find_rpc_servers(port=8000, is_local=is_local)
        
        if not self.devices_ip:
            logger.warning("未发现任何RPC服务器")
            return
            
        logger.info(f"发现 {len(self.devices_ip)} 个设备: {self.devices_ip}")
        
        for ip in self.devices_ip:
            try:
                worker = ServerProxy(f'http://{ip}:{port}/')
                self.workers.append(worker)
                logger.info(f"成功连接到Worker: {ip}")
            except Exception as e:
                logger.error(f"连接到Worker {ip} 失败: {e}")
                continue
        
    def _waiting_for_device_init(self, configDict: Dict):
        """等待所有设备初始化完成"""
        worker_size = len(self.workers)
        for k, v in configDict["--ip-devices"].items():
            if k in self.devices_ip and len(v) > 0:
                worker_size += len(v) - 1
                
        logger.info(f"等待 {worker_size} 个设备初始化完成...")
        
        while True:
            if self.done_count == worker_size:
                logger.info("所有设备已初始化完成")
                break
            logger.debug(f"已完成初始化设备数: {self.done_count}/{worker_size}")
            time.sleep(0.5)
        
    def _monitor_outputs(self):
        """后台线程监听所有worker输出"""
        logger.debug("开始监听worker输出")
        while self.running:
            try:            
                # 监听所有worker输出
                for i, (worker, ip) in enumerate(zip(self.workers, self.devices_ip)):
                    outputs = worker.get_outputs()
                    for output in outputs:
                        logger.debug(f"Worker{i}({ip}): {output}")
                        # 统计已经初始化完成的设备数量
                        if done_msg in output:
                            self.done_count += 1
                            logger.info(f"Worker{i}({ip}) 初始化完成")
                time.sleep(1)  # 避免过于频繁的轮询
            except Exception as e:
                logger.error(f"输出监听出错: {e}")
                time.sleep(1)
                
    def _start_sub(self, cmd_dict: Dict):
        """启动所有worker设备"""
        logger.info(f"正在启动 {len(self.workers)} 个子设备...")
        for i, (worker, ip) in enumerate(zip(self.workers, self.devices_ip)):
            try:
                response = worker.start_device(parse_cmd(cmd_dict, CmdType.Sub, ip))
                if response["code"] == 0:
                    logger.info(f"Worker{i}({ip}): {response['msg']}")
                else:
                    logger.error(f"Worker{i}({ip}) 启动失败 - 错误码:{response['code']}, 信息:{response['msg']}")
                    exit(1)
            except Exception as e:
                logger.error(f"启动Worker{i}({ip})时出错: {e}")
                exit(1)
        
    def _print_cmd_info(self, cmd_dict: dict, is_sync: bool):
        """打印录制配置信息"""
        config_items = []
        
        # 配置映射表
        config_map = {
            "--device": ("设备", ""),
            "-l": ("录制时长", "秒"),
            "-c": ("色彩模式", ""),
            "-d": ("深度模式", ""),
            "--depth-delay": ("深度延迟", "μs"),
            "-r": ("帧率", "fps"),
            "--imu": ("IMU", ""),
            "--external-sync": ("外部同步", ""),
            "--sync-delay": ("同步延迟", "μs"),
            "-e": ("曝光控制", ""),
            "--ip-devices": ("IP设备", ""),
            "output": ("输出路径", "")
        }
        
        # 收集有效配置
        for key, (label, unit) in config_map.items():
            value = cmd_dict.get(key)
            if key == "--ip-devices":
                value = self.devices_ip
                
            if value is not None:
                display_value = f"{value} {unit}".strip()
                config_items.append(f"{label}: {display_value}")
        
        # 输出配置信息
        mode = "同步模式" if is_sync else "独立模式"
        logger.info(f"录制配置 - {mode}")
        for item in config_items:
            logger.debug(f"  {item}")
        logger.info("开始录制...")
        
        
    def _signal_handler(self, signum, frame):
        """处理信号"""
        logger.info(f"收到信号 {signum}，正在清理...")
        self._cleanup()
        exit(0)
        
    def _cleanup(self):
        """清理资源"""
        try:
            logger.debug("开始清理资源...")
            # 停止master进程
            if hasattr(self, 'process') and self.process and self.process.poll() is None:
                logger.info("正在停止master进程...")
                self.process.terminate()
                # 等待一下，如果还没结束就强制杀死
                try:
                    self.process.wait(timeout=3)
                    logger.info("Master进程已正常停止")
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                    logger.warning("Master进程被强制终止")
            
            self.stop_monitoring()
            logger.debug("资源清理完成")
        except Exception as e:
            logger.error(f"清理过程中出错: {e}")


def ensure_output_path(output_path="./output/recording"):
    """确保输出路径存在"""
    if not os.path.exists(output_path):
        os.makedirs(output_path, exist_ok=True)
        logger.info(f"已创建目录: {output_path}")
    else:
        logger.debug(f"目录已存在: {output_path}")
    return output_path

def test_standalone(config):
    """测试独立模式"""
    master = KinectMaster()
    logger.info("=== 启动独立模式测试 ===")
    
    try:
        ensure_output_path(config["output"]["standalone"])
        master.start_standalone(config)
        master.wait_for_subprocess()
    except Exception as e:
        logger.error(f"独立模式运行出错: {e}")
    finally:
        master._cleanup()
        logger.info("=== 独立模式测试结束 ===")

def test_sync(config):
    """测试同步模式"""
    master = KinectMaster()
    logger.info("=== 启动同步模式测试 ===")
    
    try:
        # 步骤1: 准备子设备
        ok = master.prepare_sync(config, is_local=True)
        if not ok:
            return
            
        # 步骤2: 启动主设备
        master.start_sync_master(config)
        master.wait_for_subprocess()
    except Exception as e:
        logger.error(f"同步模式运行出错: {e}")
    finally:
        master._cleanup()
        logger.info("=== 同步模式测试结束 ===")

                
if __name__ == "__main__":
    logger.info("=== Kinect录制主控测试模式 ===")
    logger.info("注意: 生产环境请使用main.py和config.json进行配置")
    
    # 测试用配置（仅用于独立测试）
    test_config = {
        "--device" : 0,
        "-l" : 5,    # record length
        "-c" : "720p",    # color-mode(分辨率)
        # "-d" : "NFOV_2X2BINNED",    # depth-mode(深度相机的模式)
        # "--depth-delay": 50,  # depth-delay
        "-r": 15,    # rate
        "--imu": "OFF", # imu
        "--external-sync": None,  # 同步的类型
        "--sync-delay": 200, # 同步延迟
        "-e": -8, # 曝光度
        "--ip-devices": {
            "127.0.0.1": [1]
        },
        "output": {
            "master": "./output/sync/master",
            "sub": "./output/sync/sub",
            "standalone": "./output/standalone"
        }
    }
    
    # 最好每次只测试一个    
    test_standalone(test_config)
    # test_sync(test_config)

