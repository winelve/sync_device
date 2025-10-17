import pyrealsense2 as rs
import numpy as np
import cv2
import os

def bag_to_mp4(bag_file_path, output_path):
    # 配置管道
    pipeline = rs.pipeline()
    config = rs.config()
    
    # 加载bag文件
    config.enable_device_from_file(bag_file_path, repeat_playback=False)
    
    # 启动管道
    profile = pipeline.start(config)
    
    # 获取设备信息
    device = profile.get_device()
    playback = device.as_playback()
    playback.set_real_time(False)  # 关闭实时播放，加快处理速度
    
    # 获取视频流信息
    color_stream = profile.get_stream(rs.stream.color)
    width = color_stream.width()
    height = color_stream.height()
    fps = color_stream.fps()
    
    # 创建MP4视频写入器
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    frame_count = 0
    
    try:
        while True:
            frames = pipeline.wait_for_frames(timeout_ms=1000)
            color_frame = frames.get_color_frame()
            
            if not color_frame:
                break
                
            # 转换为numpy数组（BGR格式）
            color_image = np.asanyarray(color_frame.get_data())
            color_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
            
            # 写入视频
            out.write(color_image)
            frame_count += 1
            
            if frame_count % 100 == 0:
                print(f"已处理 {frame_count} 帧")
                
    except RuntimeError as e:
        print(f"处理完成，共 {frame_count} 帧")
    
    finally:
        pipeline.stop()
        out.release()
        print(f"转换完成：{output_path}")

# 使用示例
if __name__ == "__main__":
    bag_file = "2025-09-17_18-20-31-realsense0-realsense_0.bag"  # 替换为你的bag文件路径
    output_file = "output_video.mp4"  # 输出的MP4文件路径
    
    bag_to_mp4(bag_file, output_file)