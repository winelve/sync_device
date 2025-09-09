# Features

1. 非同步模式(`standalone`)下,可以使用本机的一个Kinect进行录制.
2. 同步模式(`sync`)下,支持分布式Kinect录制(需要多设备,联网,和同步线).
3. 同步模式(`sync`)下,支持本机连接两个`kinect`进行调试 (需要2个kinect和同步线)



# Usage

***(如果你觉得看起来麻烦,可以直接运行一下对应文件夹下的example.py)***

### 非同步模式(standalone)

先决条件:

1. 有 **至少一个** kinect设备正常与电脑连接.且没有被其他的进程占用.
2. 正确配置 **cmd_dict参数(下面会说)**

使用方式:

```py
from kinect_master import KinectMaster

try:
    cmd_dict = {...} #你的配置
    master = KinectMaster()
	master.start(cmd_dict,MODE='standalone')
	master.master.wait_for_subprocess()
except Exception as e:
    print(f"运行出错: {e}")
finally:
    master._cleanup()
    
```



### 同步模式:

#### Debug模式下

先决条件:

1. 首先需要两台Kinect相机正确与电脑连接,并且使用同步线连接.(最好是将device 0 作为主设备.1作为从设备)
2. 正确配置 **cmd_dict参数**

使用方式:

```py
# 请先手动运行kinect_sub.py 然后运行下面的代码
from kinect_master import KinectMaster

try:
    cmd_dict = {...} #你的配置
    master = KinectMaster()
	master.start(cmd_dict,MODE='sync',debug=True)
	master.master.wait_for_subprocess()
except Exception as e:
    print(f"运行出错: {e}")
finally:
    master._cleanup()
```

**解释:** 在debug模式下, `kinect_sub.py` 会将端口开放至 `127.0.0.1:8080` 以便调试

 

#### 工作模式:

先决条件:

1. 需要至少2台kinect相机, 每台kinect相机,对应一台电脑. 相机之间使用[菊花链配置](https://learn.microsoft.com/zh-cn/previous-versions/azure/kinect-dk/multi-camera-sync). 
2. 所有的电脑应在同一局域网下. 
3. 所有从设备电脑提前运行`kinect_sub.py`

使用方式:

```py
# 请先手动,在所有的子设备电脑上,运行kinect_sub.py.
# 然后在,主设备所在电脑上,运行下面的代码.

from kinect_master import KinectMaster

try:
    cmd_dict = {...} #你的配置
    master = KinectMaster()
	master.start(cmd_dict,MODE='sync',debug=False)
	master.master.wait_for_subprocess()
except Exception as e:
    print(f"运行出错: {e}")
finally:
    master._cleanup()
```



# Configuration:

```py
# 支持参数如下
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
```

**每个参数具体的解释 :**

- `-h, --help`：显示帮助信息，列出所有可用选项和用法。
- `--list`：列出当前连接的 K4A（Kinect for Azure）设备。
- `--device`：指定使用的设备索引（默认：0，即第一个设备）。
- `-l, --record-length`：设置录制时长（单位：秒，默认：无限）。
- `-c, --color-mode`：设置彩色相机分辨率（默认：1080p）。可选值：3072p、2160p、1536p、1440p、1080p、720p、720p_NV12、720p_YUY2、OFF（关闭）。
- `-d, --depth-mode`：设置深度相机模式（默认：NFOV_UNBINNED）。可选值：NFOV_2X2BINNED（窄视野2x2像素合并）、NFOV_UNBINNED（窄视野未合并）、WFOV_2X2BINNED（广视野2x2像素合并）、WFOV_UNBINNED（广视野未合并）、PASSIVE_IR（被动红外）、OFF（关闭）。
- `--depth-delay`：设置彩色帧与深度帧之间的时间偏移（单位：微秒，默认：0）。负值表示深度帧先于彩色帧，偏移需小于一帧周期。
- `-r, --rate`：设置相机帧率（单位：帧每秒，默认：相机模式支持的最大值）。可选值：30、15、5。
- `--imu`：设置惯性测量单元（IMU）录制模式（默认：ON）。可选值：ON（开启）、OFF（关闭）。
- `--external-sync`：设置外部同步模式（默认：Standalone，独立模式）。可选值：Master（主设备）、Subordinate（从设备）、Standalone（独立）。
- `--sync-delay`：设置主从相机间的同步延迟（单位：微秒，默认：0）。仅在从属模式（Subordinate）下有效。
- `-e, --exposure-control`：设置RGB相机的手动曝光值（范围：-11到1，默认：自动曝光）。

### 特别说明:

```
"-e": -8, # 曝光度 设置为-8 比较好
"output": './',  这个参数,只表示路径,文件的名字会自动取

"--ip-devices": None, 这个比较特殊, 用于指定某个特定ip的连接,启动的device编号,具体请参照example.py的例子
值为None,或者不在支持范围内的参数,将被自动舍去.
```















