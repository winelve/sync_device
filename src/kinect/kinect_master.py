from xmlrpc.client import ServerProxy
import signal
from typing import List,Dict
import time
import threading
import subprocess
from enum import Enum
import atexit
import os

try:
    from .scan import scan_network_fast  # 作为模块被导入时
except ImportError:
    from scan import scan_network_fast   # 直接运行时

# 全局变量 || 配置参数
# devices_ip = scan_network_fast(is_local=True) #扫描网段下的设备
port = 8000
tool = "./src/kinect/tool/k4arecorder"
print(tool)
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

def parse_cmd(cmd_dict: Dict,cmd_type:CmdType,ip:str='') -> List[str]:
    cmd_dict = cmd_dict.copy()
    if ip!='' and cmd_dict.get("--ip-devices",{}).get(ip,[]):
        cmd_dict["--device"] = cmd_dict["--ip-devices"][ip][0] #这边目前先取第一个设备
    cmdpack = [[k,v] for k,v in cmd_dict.items() if (v is not None) and (k != "--ip-devices") and (k != "output") and (k in config_list)]
    cmdList = [tool]

    global datetime
    output_config = cmd_dict.get("output")

    if cmd_type == CmdType.Master:
        output_dir = output_config.get('master', '.') if isinstance(output_config, dict) else '.'
        output_file = f'{output_dir}/master-{datetime}.mkv'
        cmdList.append("--external-sync")
        cmdList.append("master")
        for pack in cmdpack:
            if pack[0] == "--sync-delay":
                continue
            cmdList.append(pack[0])
            cmdList.append(str(pack[1]))
        cmdList.append(output_file)
        return cmdList
    elif cmd_type == CmdType.Sub: 
        output_dir = output_config.get('sub', '.') if isinstance(output_config, dict) else '.'
        output_file = f'{output_dir}/sub-{datetime}.mkv'
        cmdList.append("--external-sync")
        cmdList.append("subordinate")
        for pack in cmdpack:
            cmdList.append(pack[0])
            cmdList.append(str(pack[1]))
        cmdList.append(output_file)
        return cmdList
    elif cmd_type == CmdType.Standalone:
        output_dir = output_config if isinstance(output_config, str) else '.'
        output_file = f'{output_dir}/standalone_{datetime}.mkv'
        for pack in cmdpack:
            if pack[0] == "--sync-delay" :
                continue
            if pack[0] == "--external-sync":
                continue
            cmdList.append(pack[0])
            cmdList.append(str(pack[1]))
        cmdList.append(output_file)
        return cmdList
    return []

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
        self._print_cmd_info(cmdDict, is_sync=False)
        # 启动子进程
        self.process = subprocess.Popen(
            parse_cmd(cmdDict, CmdType.Standalone),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        print("独立模式录制已启动.")

    def prepare_sync(self, cmdDict: Dict, is_local: bool = True, timestamp:str=None):
        """准备同步模式：扫描并启动所有子设备"""
        update_global_datetime(timestamp)
        self._scan_devices(is_local)  # 扫描设备
        self._print_cmd_info(cmdDict, is_sync=True)
        # 启动子进程
        self._start_sub(cmdDict)
        # 启动监听线程
        self.running = True
        if not self.output_thread.is_alive():
            self.output_thread.start()

        # 确保设备全部初始化
        self._waiting_for_device_init()

    def start_sync_master(self, cmdDict: Dict):
        """启动同步模式：在子设备准备好后启动主设备"""
        print("所有子设备已准备就绪, 正在启动主设备...")
        self._start_master(cmdDict)
        
    def wait_for_subprocess(self):
        while True:
            if self.process and self.process.poll() is not None:
                # 进程结束了
                break
            time.sleep(1)
    
    def stop_monitoring(self):
        """停止输出监听"""
        self.running = False
        if self.output_thread.is_alive():
            self.output_thread.join()
            
    def _scan_devices(self,is_local:bool):  
        self.devices_ip = scan_network_fast(is_local) #扫描网段下的设备
        for ip in self.devices_ip:
            try:
                worker = ServerProxy(f'http://{ip}:{port}')
                self.workers.append(worker)
                print(f"连接到Worker: {ip}")
            except:
                continue # 连接失败则跳过
        
    def _waiting_for_device_init(self):
        while 1:
            if self.done_count == len(self.workers):
                print("所有设备已初始化完成")
                break
            time.sleep(0.5)
        
    def _monitor_outputs(self):
        """后台线程监听所有worker输出"""
        while self.running:
            try:            
                # 监听所有worker输出
                for i, (worker, ip) in enumerate(zip(self.workers,self.devices_ip)):
                    outputs = worker.get_outputs()
                    for output in outputs:
                        timestamp = time.strftime("%H:%M:%S", time.localtime())
                        print(f"[{timestamp}] Worker{i}({ip}) >> {output}")
                        #统计已经初始化完成的设备数量
                        if done_msg in output:
                            self.done_count += 1
                time.sleep(1)  # 避免过于频繁的轮询
            except Exception as e:
                print(f"输出监听出错: {e}")
                time.sleep(1)
                
    def _start_sub(self, cmd_dict: Dict):
        """启动所有worker设备"""
        for i, (worker, ip) in enumerate(zip(self.workers, self.devices_ip)):
            response = worker.start_device(parse_cmd(cmd_dict, CmdType.Sub, ip))
            if response["code"] == 0:
                print(f"Worker{i}:{response['msg']}")
            else:
                print(f"Worker{i} -- 错误码:{response['code']} \nmsg:{response['msg']}")
                exit(1)
                
    def _start_master(self,cmd_dict: Dict):
        # -------启动master线程-------
        self.process = subprocess.Popen(
            parse_cmd(cmd_dict, CmdType.Master),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        print("master启动")
        print(f'master运行命令: {parse_cmd(cmd_dict, CmdType.Master)}')
        
    def _print_cmd_info(self, cmd_dict: dict, is_sync:bool):
        """打印录制配置信息"""
        config_items = []
        
        # 配置映射表
        config_map = {
            "--device": ("📱 设备", ""),
            "-l": ("⏱️  录制时长", "秒"),
            "-c": ("🎥 色彩模式", ""),
            "-d": ("📷 深度模式", ""),
            "--depth-delay": ("⏰ 深度延迟", "μs"),
            "-r": ("🎬 帧率", "fps"),
            "--imu": ("🧭 IMU", ""),
            "--external-sync": ("🔗 外部同步", ""),
            "--sync-delay": ("⏳ 同步延迟", "μs"),
            "-e": ("💡 曝光控制", ""),
            "--ip-devices": ("🌐 IP设备", ""),
            "output": ("📁 输出路径", "")
        }
        
        # 收集有效配置
        for key, (label, unit) in config_map.items():
            value = cmd_dict.get(key)
            if value is not None:
                display_value = f"{value} {unit}".strip()
                config_items.append(f"  {label}: {display_value}")
        
        # 输出格式化信息
        if config_items:
            print("\n┌─ 📋 录制配置信息 ─" + "─" * 20)
            if is_sync:
                print("  🔗 Sync模式")
            else:
                print("  🔗 Standalone模式")
                
            for item in config_items:
                print(item)
            print("  🎬 开始录制...")
            print("└─" + "─" * 32)
        else:
            print("📋 当前无有效配置信息")
        
    def _signal_handler(self, signum, frame):
        """处理信号"""
        print(f"\n收到信号 {signum}，正在清理...")
        self._cleanup()
        exit(0)
    def _cleanup(self):
        """清理资源"""
        try:
            # 停止master进程
            if hasattr(self, 'process') and self.process and self.process.poll() is None:
                self.process.terminate()
                # 等待一下，如果还没结束就强制杀死
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                print("Master进程已停止")
            
            self.stop_monitoring()                  
        except Exception as e:
            print(f"清理过程中出错: {e}")
    


        
                
if __name__ == "__main__":
    
    def ensure_output_path(output_path="./output/recording"):
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)
            print(f"已创建目录: {output_path}")
        else:
            print(f"目录已存在: {output_path}")
        return output_path
    
    cmd_d = {
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
        "output": "./output/recording"  # 输出路径
    }
    
    master = KinectMaster()

    # --- 独立模式示例 ---
    print("--- 启动独立模式 ---")
    try:
        ensure_output_path(cmd_d["output"])
        master.start_standalone(cmd_d)
        master.wait_for_subprocess()
    except Exception as e:
        print(f"独立模式运行出错: {e}")
    finally:
        master._cleanup()
        print("--- 独立模式结束 ---")

    # print("\n" + "="*50 + "\n")

    # --- 同步模式示例 ---
    # print("--- 启动同步模式 ---")
    # # is_local=True 用于调试, 会扫描本地网络.
    # try:
    #     # 步骤1: 准备子设备
    #     master.prepare_sync(cmd_d, is_local=True)
        
    #     # 在这里可以加入手动确认的步骤
    #     input("按回车键启动主设备...")

    #     # 步骤2: 启动主设备
    #     master.start_sync_master(cmd_d)
        
    #     master.wait_for_subprocess()
    # except Exception as e:
    #     print(f"同步模式运行出错: {e}")
    # finally:
    #     master._cleanup()
    #     print("--- 同步模式结束 ---")