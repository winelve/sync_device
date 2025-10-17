import pyrealsense2 as rs
import numpy as np
import cv2
import os

import argparse

def _open_playback(bag_file_path):
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device_from_file(bag_file_path, repeat_playback=False)
    profile = pipeline.start(config)
    device = profile.get_device()
    playback = device.as_playback()
    playback.set_real_time(False)
    return pipeline, profile

def _get_color_profile(profile):
    streams = profile.get_streams()
    for stream in streams:
        if stream.stream_type() == rs.stream.color:
            return stream.as_video_stream_profile()
    return None

def bag_to_mp4(bag_file_path, output_path):
    # 检查文件是否存在
    if not os.path.exists(bag_file_path):
        print(f"错误：找不到文件 {bag_file_path}")
        return

    # 第一遍：统计帧数与时间范围，计算有效 FPS
    pipeline, profile = _open_playback(bag_file_path)
    color_prof = _get_color_profile(profile)
    if not color_prof:
        print("错误：在bag文件中找不到颜色流。")
        pipeline.stop()
        return
    width, height = color_prof.width(), color_prof.height()

    cnt = 0
    t0_ms = None
    t1_ms = None
    try:
        while True:
            frames = pipeline.wait_for_frames(timeout_ms=1000)
            c = frames.get_color_frame()
            if not c:
                break
            ts = c.get_timestamp()  # 毫秒
            if t0_ms is None:
                t0_ms = ts
            t1_ms = ts
            cnt += 1
    except RuntimeError:
        pass
    finally:
        pipeline.stop()

    if cnt == 0 or t0_ms is None or t1_ms is None:
        print("错误：未能从bag获取到任何颜色帧")
        return

    duration_s = max(0.001, (t1_ms - t0_ms) / 1000.0)
    eff_fps = cnt / duration_s

    # 第二遍：按有效 FPS 写出 MP4
    pipeline, profile = _open_playback(bag_file_path)
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, eff_fps, (width, height))
        written = 0
        while True:
            frames = pipeline.wait_for_frames(timeout_ms=1000)
            color_frame = frames.get_color_frame()
            if not color_frame:
                break
            img = np.asanyarray(color_frame.get_data())
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            out.write(img)
            written += 1
            if written % 100 == 0:
                print(f"已处理 {written} / {cnt} 帧 (FPS≈{eff_fps:.2f})")
    except RuntimeError:
        pass
    finally:
        pipeline.stop()
        try:
            out.release()
        except Exception:
            pass
        print(f"处理完成：{written} 帧，有效FPS≈{eff_fps:.2f}，估计时长≈{written/eff_fps:.2f}s")
        print(f"转换完成：{output_path}")

# 使用示例
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 RealSense .bag 文件转换为 .mp4 文件。")
    parser.add_argument("bag_file", help="输入的 .bag 文件路径。")
    parser.add_argument("output_file", nargs='?', help="输出的 .mp4 文件路径。如果未提供，将在 .bag 文件旁边生成。")
    
    args = parser.parse_args()
    
    output_file = args.output_file
    if output_file is None:
        output_file = os.path.splitext(args.bag_file)[0] + ".mp4"
    
    bag_to_mp4(args.bag_file, output_file)