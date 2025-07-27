import subprocess
import threading
import queue
from typing import List,Dict
from xmlrpc.server import SimpleXMLRPCServer

port = 8000

class Worker:
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.is_running = False
        self.port = port
        
    def start_device(self,cmd:List[str]) -> Dict[str, str|int]:
        try: 
            """启动设备进程"""
            self.process = subprocess.Popen(
                cmd,  # 替换为你的程序
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.is_running = True
            threading.Thread(target=self._monitor, daemon=True).start()
        except:
            return {"code": 1, "msg": "启动失败" }
        return {"code": 0, "msg": "启动成功" }
    
    def _monitor(self):
        """监听输出线程"""
        while self.is_running and self.process:
            line = self.process.stdout.readline()
            if line:
                self.output_queue.put(line.strip())
    
    def get_outputs(self):
        """获取所有输出"""
        outputs = []
        while not self.output_queue.empty():
            outputs.append(self.output_queue.get_nowait())
        return outputs

# 启动RPC服务器
worker = Worker()
server = SimpleXMLRPCServer(('0.0.0.0', port))
server.register_instance(worker)
print(f"Worker启动在端口{port}")
server.serve_forever()