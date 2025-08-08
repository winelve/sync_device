from kinect.kinect_record_master import KinectMaster

if __name__ == "__main__":
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
        # "-e": -10, # 曝光度
        "--ip-devices": {
            "127.0.0.1": [1]
        },
        "output":{
            "standalone": "./output/standalone"
        }  # 输出路径
    }
    
    #设置调试模式, 默认使用localhost作为worker的ip
    master = KinectMaster()
    try:
        # standalone模式
        master.start_standalone(cmd_d)
        
        # sync debug模式
        # master.prepare_sync(cmd_d,is_local=True)
        # master.start_sync_master()
        master.wait_for_subprocess()  # 主线程等待，让程序保持运行
        print("=============录制完毕=============")
    except Exception as e:
        print(f"运行出错: {e}")
    finally:
        master._cleanup()