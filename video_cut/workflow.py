"""
完整工作流示例：自动检测并剪辑多个视频
"""

import os
import sys
import json
from pathlib import Path

# 添加模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'caputure'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cut'))



from caputure.capture import detect_flash, BrightnessChangeDetector
from cut.video_cutter import VideoCutter


def load_config(config_path='config.json'):
    """加载配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def process_video_sync(video_files: list, config: dict = None):
    """
    处理多个视频，检测闪光并剪辑对齐
    
    Args:
        video_files: 视频文件路径列表
        config: 配置字典
    """
    if config is None:
        config = load_config()
    
    # 从配置读取参数
    sensitivity = config.get('detection', {}).get('sensitivity', 0.3)
    reencode = config.get('cutting', {}).get('reencode', False)
    output_suffix = config.get('cutting', {}).get('output_suffix', '_synced')
    output_dir = config.get('output', {}).get('output_dir', './synchronized_videos')
    
    # 可视化参数
    enable_viz = config.get('visualization', {}).get('enable', False)
    save_plot = config.get('visualization', {}).get('save_plot', False)
    plot_dir = config.get('visualization', {}).get('plot_dir', './brightness_plots')
    
    # 创建输出目录
    if save_plot:
        os.makedirs(plot_dir, exist_ok=True)
    
    print("="*60)
    print("多摄像头视频同步对齐工具")
    print(f"灵敏度: {sensitivity} ({sensitivity*100:.0f}%变化触发)")
    print("="*60)
    
    # 创建检测器
    detector = BrightnessChangeDetector(sensitivity=sensitivity)
    
    # 第一步：检测所有视频的闪光时刻
    print("\n第一步：检测闪光时刻...")
    print("-"*60)
    
    timestamps = []
    successful_videos = []
    
    for i, video_path in enumerate(video_files, 1):
        print(f"\n[{i}/{len(video_files)}] 处理: {video_path}")
        
        if not os.path.exists(video_path):
            print(f"  ✗ 文件不存在，跳过")
            continue
        
        # 生成图片保存路径
        plot_path = None
        if save_plot:
            from pathlib import Path
            video_name = Path(video_path).stem
            plot_path = os.path.join(plot_dir, f"{video_name}_brightness.png")
        
        result = detector.detect(
            video_path,
            viz=enable_viz,
            save=save_plot,
            save_path=plot_path
        )
        
        if result:
            timestamp, frame_num = result
            print(f"  ✓ 检测成功: {timestamp:.3f}秒 (帧{frame_num})")
            timestamps.append(timestamp)
            successful_videos.append(video_path)
        else:
            print(f"  ✗ 检测失败，跳过")
    
    if not successful_videos:
        print("\n✗ 没有成功检测到任何视频的闪光时刻")
        return
    
    # 第二步：剪辑视频
    print("\n" + "="*60)
    print("第二步：剪辑视频...")
    print("-"*60)
    
    cutter = VideoCutter()
    results = cutter.batch_cut_videos(
        video_files=successful_videos,
        timestamps=timestamps,
        output_dir=output_dir,
        suffix=output_suffix,
        reencode=reencode
    )
    
    print("\n" + "="*60)
    print("处理完成!")
    print("="*60)
    print(f"总视频数: {len(video_files)}")
    print(f"成功检测: {len(successful_videos)}")
    print(f"成功剪辑: {sum(1 for v in results.values() if v)}")
    print(f"输出目录: {output_dir}")
    print("="*60)


if __name__ == '__main__':
    config = load_config('config.json')    
    # 直接指定视频文件列表
    video_files = [
        './videos/kinect.mkv',
        # 'D:\\videos\\camera2.mp4',
        # 'D:\\videos\\camera3.mp4',
    ]
    if not video_files:
        sys.exit(1)    
    process_video_sync(video_files=video_files, config=config)

    # 扫描目录
    # video_dir = 'D:\\videos'
    # video_files = [
    #     os.path.join(video_dir, f) 
    #     for f in os.listdir(video_dir) 
    #     if f.endswith(('.mp4', '.avi', '.mov'))
    # ]