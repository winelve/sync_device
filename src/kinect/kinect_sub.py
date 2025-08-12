import subprocess
import threading
import queue
from typing import List, Dict, Any
from xmlrpc.server import SimpleXMLRPCServer

port = 8000
class Worker:
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.output_queue = queue.Queue()
        self.is_running = False
        self.port = port
        self.run_count = 0
    
    def start_device(self, cmds: List[List[str]]) -> Dict[str, Any]:
        """
        这个函数用于根据一个命令列表启动多个进程.
        它接收一个二维数组, 例如 [['cmd1', 'arg1'], ['cmd2', 'arg2']],
        每个子数组都是一个独立的命令.
        """
        self.run_count += 1
        print(f'================连续工作{self.run_count}次================')

        if self.is_running:
            self.stop_devices()

        self.processes.clear()
        self.is_running = True
        results = []

        for cmd in cmds:
            result = self._create_and_monitor_process(cmd)
            results.append(result)

        if any(p["status"] == "started" for p in results):
            return {"code": 0, "msg": "启动操作完成，具体状态请查看详情。", "details": results}
        else:
            self.is_running = False
            return {"code": 1, "msg": "所有进程均启动失败。", "details": results}

    def _create_and_monitor_process(self, cmd: List[str]) -> Dict[str, Any]:
        """
        为单个命令创建并监控一个独立的子进程。
        """
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            self.processes.append(process)
            print(f"成功启动进程 (PID: {process.pid}) | 命令: {' '.join(cmd)}")
            
            threading.Thread(target=self._monitor, args=(process, cmd), daemon=True).start()
            
            return {"cmd": ' '.join(cmd), "status": "started", "pid": process.pid}
        
        except Exception as e:
            error_msg = f"启动失败 | 命令: '{' '.join(cmd)}' | 错误: {e}"
            print(error_msg)
            return {"cmd": ' '.join(cmd), "status": "failed", "error": error_msg}

    def _monitor(self, process: subprocess.Popen, cmd: List[str]):
        """
        监听指定进程的输出, 并将带有命令前缀的输出放入队列.
        这个线程会随进程的结束而自动停止.
        """
        cmd_str = ' '.join(cmd)
        while self.is_running and process.poll() is None:
            try:
                line = process.stdout.readline()
                if line:
                    output = f"[{cmd_str} (PID:{process.pid})]: {line.strip()}"
                    self.output_queue.put(output)
                    print(output)
                else:
                    break
            except Exception as e:
                print(f"读取进程 {process.pid} 的输出时发生错误: {e}")
                break
        
        # 进程结束后，做最后的检查，确保所有输出都被读取
        for line in process.stdout.readlines():
            output = f"[{cmd_str} (PID:{process.pid})]: {line.strip()}"
            self.output_queue.put(output)
            print(output)
            
        print(f"进程 {process.pid} 的监控已停止.")
    
    def get_outputs(self) -> List[str]:
        """获取所有进程合并后的输出"""
        outputs = []
        while not self.output_queue.empty():
            outputs.append(self.output_queue.get_nowait())
        return outputs

    def stop_devices(self) -> Dict[str, str]:
        """
        停止所有由这个worker启动的子进程.
        """
        print("正在停止所有运行中的进程...")
        self.is_running = False

        for process in self.processes:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                    print(f"已终止进程 PID: {process.pid}")
                except subprocess.TimeoutExpired:
                    process.kill()
                    print(f"已强制杀死进程 PID: {process.pid}")
                except Exception as e:
                    print(f"停止进程 PID {process.pid} 时出错: {e}")

        self.processes.clear()
        while not self.output_queue.empty():
            self.output_queue.get_nowait()
            
        print("所有进程已停止.")
        return {"code": 0, "msg": "所有进程已停止"}

    def take_photo(self):
        """
        请完善这个函数. kinect_sub.py 将在远程电脑运行.
        这个函数用于调用 运行电脑 上的kinect摄像头. 拍摄并且保存.
        参数请合理设置. 其余辅助函数自行添加.
        """
        
        pass


if __name__ == '__main__':
    worker = Worker()
    server = SimpleXMLRPCServer(('0.0.0.0', port),logRequests=False)
    server.register_instance(worker)
    print(f"Worker启动在端口 {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        worker.stop_devices()
        print("\nWorker服务已停止")