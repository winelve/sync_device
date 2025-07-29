import socket
import subprocess
import concurrent.futures
import ipaddress
import platform
import xmlrpc.client
from typing import List

def get_network_ips(is_local: bool = False) -> List[str]:
    """获取本地网络的IP地址列表."""
    if is_local:
        return ["127.0.0.1"]
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except OSError:
        print("错误: 无法确定本机IP地址, 请检查网络连接.")
        return []

    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    print(f"本机IP: {local_ip}, 将扫描 {network} 网段...")
    
    # 返回网络中的所有主机IP
    return [str(ip) for ip in network.hosts() if str(ip) != local_ip]

def check_xmlrpc_service(host: str, port: int, timeout: int = 2) -> bool:
    """
    以静默、可靠且带超时的方式检查XML-RPC服务.
    :return: 如果找到XML-RPC服务则返回 True, 否则返回 False.
    """
    original_timeout = socket.getdefaulttimeout()
    try:
        # 强制为当前线程设置一个严格的超时
        socket.setdefaulttimeout(timeout)
        
        server_url = f"http://{host}:{port}"
        server = xmlrpc.client.ServerProxy(server_url, allow_none=True)
        
        # 这一步现在也会受到上面设置的超时限制
        server.system.listMethods()
        return True
    except xmlrpc.client.Fault:
        # Fault表示它是一个RPC服务器, 但不支持listMethods. 仍然算作成功.
        return True
    except Exception:
        # 捕获所有其他异常 (包括 socket.timeout, ConnectionRefusedError 等)
        # 意味着它不是我们想要的RPC服务.
        return False
    finally:
        # 无论如何, 总是恢复原始的全局超时设置
        socket.setdefaulttimeout(original_timeout)

def find_rpc_servers(port: int = 8000, is_local: bool = False) -> List[str]:
    """
    通过直接端口扫描检测网络中运行XML-RPC服务的主机.
    """
    print("--- 直接扫描网络端口, 寻找RPC服务 ---")
    all_hosts = get_network_ips(is_local=is_local)
    if not all_hosts:
        return []

    rpc_hosts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        future_to_host = {executor.submit(check_xmlrpc_service, host, port): host for host in all_hosts}
        
        completed = 0
        total = len(future_to_host)
        for future in concurrent.futures.as_completed(future_to_host):
            completed += 1
            host = future_to_host[future]
            
            # 打印进度
            print(f"\r正在检查: {host:<15} ({completed}/{total})", end="", flush=True)

            if future.result():
                rpc_hosts.append(host)
                # 清除进度行并打印发现信息
                print(f"\r{' ' * 40}\r[+] 发现RPC服务: {host}:{port}")

    print(f"\n\n--- 扫描完成 ---")
    if rpc_hosts:
        rpc_hosts.sort(key=lambda x: int(x.split('.')[-1]))
        print(f"共找到 {len(rpc_hosts)} 个RPC服务主机:")
        for ip in rpc_hosts:
            print(f"  [+] {ip}:{port}")
    else:
        print("未在任何活动设备上发现指定的RPC服务.")
        
    return rpc_hosts

if __name__ == "__main__":
    # 设置 is_local=True 可用于快速测试
    # 设置 is_local=False 可扫描真实局域网
    rpc_servers = find_rpc_servers(port=8000, is_local=False)
    print("\n返回的RPC服务器列表:")
    print(rpc_servers)
