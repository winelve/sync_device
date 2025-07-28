import socket
import subprocess
import concurrent.futures
import ipaddress
import platform
from typing import List

def scan_network_fast(is_local: bool = False) -> List[str]:
    if is_local:
        return ["127.0.0.1"]
    
    """快速扫描网络设备"""
    
    # 获取本机IP和网络段
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()
    
    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    
    print(f"本机IP: {local_ip}")
    # 快速ping函数
    def quick_ping(ip):
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        cmd = ['ping', param, '1', '-w', '1000', str(ip)]  # Windows: -w 1000ms timeout
        if platform.system().lower() != 'windows':
            cmd = ['ping', '-c', '1', '-W', '1', str(ip)]  # Linux: -W 1s timeout
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            return str(ip) if result.returncode == 0 else None
        except:
            return None
    
    # 并发扫描
    devices = []
    print("扫描中...", end="", flush=True)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(quick_ping, ip): ip for ip in network.hosts()}
        
        completed = 0
        total = len(futures)
        
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            if completed % 20 == 0:  # 每完成20个显示进度
                print(f"\r扫描中... {completed}/{total}", end="", flush=True)
            
            result = future.result()
            if result and result != local_ip:  # 排除本机IP
                devices.append(result)
    
    print(f"\r扫描完成！发现 {len(devices)} 个设备")
    
    # 排序并显示
    devices.sort(key=lambda x: int(x.split('.')[-1]))
    for ip in devices:
        print(f"  💻 {ip}")
    
    return devices
