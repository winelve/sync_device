from xmlrpc.client import ServerProxy
import signal
from typing import List,Dict
import time
import threading
import subprocess
from enum import Enum

from scan import scan_network_fast

devices_ip = scan_network_fast(is_local=True) #扫描网段下的设备
port = 8000

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
    "-e": None # 曝光度
}

class CmdType(Enum):
    Standalone = 0
    Master = 1
    Sub = 2

def parse_cmd(cmd_dict: Dict,cmd_type:CmdType) -> List[str]:
    cmdpack = [[k,v] for k,v in cmd_dict.items() if v is not None]
    cmdList = ["k4arecorder"]
    if cmd_type == CmdType.Master:
        for pack in cmdpack:
            if pack[0] != "--sync-delay":
                continue
            cmdList.append(pack[0])
            cmdList.append(pack[1])
        return cmdList
    elif cmd_type == CmdType.Sub: 
        for pack in cmdpack:
            cmdList.append(pack[0])
            cmdList.append(pack[1])
        return cmdList
    elif cmd_type == CmdType.Standalone:
        for pack in cmdpack:
            if pack[0] == "--sync-delay" :
                continue
            if pack[0] == "--external-sync":
                continue
            cmdList.append(pack[0])
            cmdList.append(pack[1])
        return cmdList
    return []



class Master:
    def __init__(self):
        #master进程
        self.process = None
        self.done_count = 0
        # 连接worker
        self.workers = []
        self.devices_ip = devices_ip
        for ip in devices_ip:
            try:
                worker = ServerProxy(f'http://{ip}:{port}')
                self.workers.append(worker)
                print(f"连接到Worker: {ip}")
            except:
                continue # 连接失败则跳过
        
        # 启动输出监听线程
        self.output_thread = threading.Thread(target=self._monitor_outputs, daemon=True)

    def start_all(self, cmdDict: List[str]):
        #启动子进程
        self._start_sub(parse_cmd(cmdDict, CmdType.Sub))
        # 启动监听线程
        self.running = True
        self.output_thread.start()
        
        #确保设备全部初始化
        self._waiting_for_device_init()
        # 启动master进程
        self._start_master(cmdDict, CmdType.Master)
        
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
                for i, (worker, ip) in enumerate(zip(self.workers,self.devices_ip)):
                    outputs = worker.get_outputs()
                    for output in outputs:
                        timestamp = time.strftime("%H:%M:%S", time.localtime())
                        print(f"[{timestamp}] Worker{i}({ip}) >> {output}")
                        #统计已经初始化完成的设备数量
                        if 'Done' in output:
                            self.done_count += 1
                time.sleep(1)  # 避免过于频繁的轮询
            except Exception as e:
                print(f"输出监听出错: {e}")
                time.sleep(1)
                
    def stop_master(self):
        self.process.send_signal(signal.SIGINT)
        print("Master进程已停止")
    
    def stop_monitoring(self):
        """停止输出监听"""
        self.running = False
        if self.output_thread.is_alive():
            self.output_thread.join()
            
    def _start_sub(self, sub_cmdList: List[str]):
        """启动所有worker设备"""
        for i, worker in enumerate(self.workers):
            response = worker.start_device(sub_cmdList)
            if response["code"] == 0:
                print(f"Worker{i}:{response['msg']}")
            else:
                print(f"Worker{i} -- 错误码:{response['code']} \nmsg:{response['msg']}")
                exit(1)
    def _start_master(self,master_cmdList: List[str]):
        # -------启动master线程-------
        self.process = subprocess.Popen(
            master_cmdList, 
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
                
if __name__ == "__main__":
    # 使用示例
    master = Master()
    
    cmd_d = {
        "--device" : 0,
        "-l" : 5,    # record length
        "-c" : "720p",    # color-mode(分辨率)
        "-d" : None,    # depth-mode(深度相机的模式)
        "--depth-delay": None,  # depth-delay
        "-r": 15,    # rate
        "--imu": "OFF", # imu
        "--external-sync": None,  # 同步的类型
        "--sync-delay": None, # 同步延迟
        "-e": 8 # 曝光度
    }
    
    master.start_all(cmd_d)

    try:
        # 主循环
        while True:
            # 发送命令
            cmd = input("输入命令 (或q退出): ")
            if cmd == 'q':
                master.stop_master()
                break
    except KeyboardInterrupt:
        print("\n正在退出...")
        master.stop_master()
    finally:
        # 清理资源
        master.stop_monitoring()
    
