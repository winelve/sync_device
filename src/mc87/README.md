# 安装依赖库

请先进入项目目录,执行:

`pip install -r requirements.txt`

# 版本

开发使用版本:`Python 3.10.18`

# 项目结构

```
|
|__main.py (程序入口)
|__audiorec.py (音频录制代码)
|__config.json (配置文件)
```

# 运行

请打开命令行窗口

```
python main.py 指令 参数
```

下面对指令和参数进行说明

# 指令&参数

### 指令

目前支持三个指令

`record(录制音频)` `devices(查看所有设备)` `default(查看默认设备)`

### 参数:

```
// 指令
// 说明: record的参数均是可选的
record
 参数
-o "path"   (outpath)  				//输出路径 
-d 1,2,3,4  (devices)				//指定设备编号,每个设备用'英文逗号'分隔
-t 5		(time)					//-- 指定录制时长
-r 44100    (rate)					//采样率
-c 2		(channel)				//通道数
-m 0|1		(mode:0定时,1手动)		 //模式(定时录音0 和 手动暂停1) -m 1 或者 -m 0
--fmt 8		(format: 格式) 		  // 8,4,2 质量以此升高(正常选8就够了)
--frames 1024						//每帧的采样数量 (这个不用改)/例子:python main.py record


例子:python main.py record -o ./
例子:python main.py record -o ./audio/ -d 1,2
例子:python main.py record -r 16000
例子:python main.py record -o ./ -m 0
```

```
// 指令
devices
// 参数
-d (detail)  是否输出"音频输出设备"


// 例子: python main.py devices (不输出) 或
		python main.py devices -d (输出)
```

```
// 指令
default
无参数

例子:python main.py default
```



# 配置数据 `config.json`

```
{	
    "format":8,    				 //格式
    "channels":1,   			 //通道数
    "rate":44100,  				 //采样率
    "is_input":true, 			 //是否是输入音频(不要修改)
    "input_device_index":[1],    //输入设备编号
    "frames_per_buffer":1024,    //每帧采样个数
    "mode": "timing",            //模式 [timing-->定时模式] [manual--> 手动停止]
    "timing": 5,                 //定时时长
    "outpath": "./audio/"        //输出路径
}
```

## 重要: 程序会先读取`config.json`中的配置. 命令行参数的配置,会覆盖对应 key 的 value.

比如: `python main.py record -t 10`就会更改配置中`timing`的值为10,其余都不变.



