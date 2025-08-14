import subprocess
import threading
import queue
from typing import List, Dict, Any
from xmlrpc.server import SimpleXMLRPCServer
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

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
        logger.info(f'开始第 {self.run_count} 次工作任务')

        if self.is_running:
            logger.info("检测到正在运行的进程，先停止现有进程")
            self.stop_devices()

        self.processes.clear()
        self.is_running = True
        results = []

        logger.info(f"准备启动 {len(cmds)} 个进程")
        for i, cmd in enumerate(cmds):
            logger.debug(f"启动第 {i+1} 个进程: {' '.join(cmd)}")
            result = self._create_and_monitor_process(cmd)
            results.append(result)
            #--------这里非常重要, 设备不能启动一下同时启动,否则会初始化失败------
            time.sleep(1) 

        success_count = sum(1 for p in results if p["status"] == "started")
        if success_count > 0:
            logger.info(f"启动操作完成，成功启动 {success_count}/{len(cmds)} 个进程")
            return {"code": 0, "msg": "启动操作完成，具体状态请查看详情。", "details": results}
        else:
            self.is_running = False
            logger.error("所有进程均启动失败")
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
            logger.info(f"成功启动进程 (PID: {process.pid})")
            logger.debug(f"执行命令: {' '.join(cmd)}")
            
            threading.Thread(target=self._monitor, args=(process, cmd), daemon=True).start()
            
            return {"cmd": ' '.join(cmd), "status": "started", "pid": process.pid}
        
        except Exception as e:
            error_msg = f"启动失败: {e}"
            logger.error(f"命令执行失败: {' '.join(cmd)} - {error_msg}")
            return {"cmd": ' '.join(cmd), "status": "failed", "error": error_msg}

    def _monitor(self, process: subprocess.Popen, cmd: List[str]):
        """
        监听指定进程的输出, 并将带有命令前缀的输出放入队列.
        这个线程会随进程的结束而自动停止.
        """
        cmd_str = ' '.join(cmd)
        logger.debug(f"开始监控进程 {process.pid}")
        
        while self.is_running and process.poll() is None:
            try:
                line = process.stdout.readline()
                if line:
                    output = f"[{cmd_str} (PID:{process.pid})]: {line.strip()}"
                    self.output_queue.put(output)
                    logger.debug(f"进程输出: {output}")
                else:
                    break
            except Exception as e:
                logger.error(f"读取进程 {process.pid} 的输出时发生错误: {e}")
                break
        
        # 进程结束后，做最后的检查，确保所有输出都被读取
        try:
            for line in process.stdout.readlines():
                output = f"[{cmd_str} (PID:{process.pid})]: {line.strip()}"
                self.output_queue.put(output)
                logger.debug(f"进程最终输出: {output}")
        except Exception as e:
            logger.warning(f"读取进程 {process.pid} 最终输出时出错: {e}")
            
        logger.info(f"进程 {process.pid} 的监控已停止")
    
    def get_outputs(self) -> List[str]:
        """获取所有进程合并后的输出"""
        outputs = []
        while not self.output_queue.empty():
            outputs.append(self.output_queue.get_nowait())
        
        if outputs:
            logger.debug(f"返回 {len(outputs)} 条输出信息")
        return outputs

    def stop_devices(self) -> Dict[str, str]:
        """
        停止所有由这个worker启动的子进程.
        """
        if not self.processes:
            logger.info("没有运行中的进程需要停止")
            return {"code": 0, "msg": "没有运行中的进程"}
            
        logger.info(f"正在停止 {len(self.processes)} 个运行中的进程...")
        self.is_running = False

        stopped_count = 0
        for process in self.processes:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                    logger.info(f"已正常终止进程 PID: {process.pid}")
                    stopped_count += 1
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning(f"已强制杀死进程 PID: {process.pid}")
                    stopped_count += 1
                except Exception as e:
                    logger.error(f"停止进程 PID {process.pid} 时出错: {e}")
            else:
                logger.debug(f"进程 PID {process.pid} 已经结束")

        self.processes.clear()
        
        # 清空输出队列
        queue_size = self.output_queue.qsize()
        while not self.output_queue.empty():
            self.output_queue.get_nowait()
            
        if queue_size > 0:
            logger.debug(f"已清空 {queue_size} 条队列输出")
            
        logger.info(f"已停止 {stopped_count} 个进程")
        return {"code": 0, "msg": f"已停止 {stopped_count} 个进程"}

    def take_photo(self):
        """
        请完善这个函数. kinect_sub.py 将在远程电脑运行.
        这个函数用于调用 运行电脑 上的kinect摄像头. 拍摄并且保存.
        参数请合理设置. 其余辅助函数自行添加.
        """
        
        pass


if __name__ == '__main__':
    worker = Worker()
    server = SimpleXMLRPCServer(('0.0.0.0', port), logRequests=False)
    server.register_instance(worker)
    
    logger.info(f"Worker服务启动在端口 {port}")
    logger.info("等待来自master的连接...")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
        worker.stop_devices()
        logger.info("Worker服务已停止")
    except Exception as e:
        logger.error(f"服务运行出错: {e}")
        worker.stop_devices()