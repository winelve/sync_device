from kinect_record_master import KinectMaster, CmdType, parse_cmd
import time
import os

def ensure_output_path(output_path="./output/recording"):
    if not os.path.exists(output_path):
        os.makedirs(output_path, exist_ok=True)
        print(f"已创建目录: {output_path}")
    else:
        print(f"目录已存在: {output_path}")
    return output_path

def test_standalone(config):
    master = KinectMaster()
    # --- 独立模式示例 ---
    print("--- 启动独立模式 ---")
    try:
        master.start_standalone(config)
        master.wait_for_subprocess()
    except Exception as e:
        print(f"独立模式运行出错: {e}")
    finally:
        master._cleanup()
        print("--- 独立模式结束 ---")

def test_sync(config):
    # --- 同步模式示例 ---
    master = KinectMaster()
    print("--- 启动同步模式 ---")
    # is_local=True 用于调试, 会扫描本地网络.
    try:
        # 步骤1: 准备子设备
        ok = master.prepare_sync(config, is_local=True)
        if not ok:
            master._cleanup()
            print("--- 同步模式结束 ---")
            print("\n" + "="*50 + "\n")
            return
        # 步骤2: 启动主设备
        master.start_sync_master(config)
        master.wait_for_subprocess()
    except Exception as e:
        print(f"同步模式运行出错: {e}")
    finally:
        master._cleanup()
        print("--- 同步模式结束 ---")

def test_parser(config):
    print("--- 测试命令解析器 ---")
    cmd_list = parse_cmd(config, CmdType.Standalone)
    for cmd in cmd_list:
        print(f"解析出的命令: {cmd}")

if __name__ == "__main__":    
    config = {
        "--device" : 1,
        "-l" : 5,    # record length
        "-c" : "720p",    # color-mode(分辨率)
        # "-d" : "NFOV_2X2BINNED",    # depth-mode(深度相机的模式)
        # "--depth-delay": 50,  # depth-delay
        "-r": 15,    # rate
        "--imu": "OFF", # imu
        "--external-sync": None,  # 同步的类型
        "--sync-delay": 200, # 同步延迟
        "-e": 1, # 曝光度
        "--ip-devices": {
            "127.0.0.1": [0, 2, 3]
        },
        "output": {
            "master": "./output/sync/master",
            "sub": "./output/sync/sub",
            "standalone": "./output/standalone"
        }
    }
    
    
    # 最好每次只测试一个    
    # test_standalone(config)
    test_sync(config)
    # test_parser(config)
