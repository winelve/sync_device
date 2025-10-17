"""
视频剪辑工具模块
提供通用的视频剪辑功能，可以根据时间点裁剪视频
"""

import os
import subprocess
from typing import Optional, Union
import json
from pathlib import Path


class VideoCutter:
    """通用视频剪辑工具类"""
    
    def __init__(self, ffmpeg_path: str = 'ffmpeg'):
        """
        初始化剪辑工具
        
        Args:
            ffmpeg_path: ffmpeg可执行文件路径，默认使用系统PATH中的ffmpeg
        """
        self.ffmpeg_path = ffmpeg_path
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"✓ FFmpeg 已就绪")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        print("警告: 未检测到FFmpeg，请确保已安装并添加到系统PATH")
        print("下载地址: https://ffmpeg.org/download.html")
        return False
    
    def cut_from_timestamp(self, 
                          input_path: str,
                          output_path: str,
                          start_time: float,
                          end_time: Optional[float] = None,
                          reencode: bool = False) -> bool:
        """
        从指定时间点开始剪辑视频
        
        Args:
            input_path: 输入视频文件路径
            output_path: 输出视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒），None表示到视频结束
            reencode: 是否重新编码（False为快速剪辑，True为精确剪辑）
            
        Returns:
            是否成功
        """
        if not os.path.exists(input_path):
            print(f"错误: 输入文件不存在: {input_path}")
            return False
        
        # 构建ffmpeg命令 - 使用可靠的方法
        cmd = [self.ffmpeg_path]
        
        if reencode:
            # 精确模式：-ss在-i后，重新编码
            cmd.extend(['-i', input_path, '-ss', str(start_time)])
            if end_time is not None:
                duration = end_time - start_time
                cmd.extend(['-t', str(duration)])
            cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-c:a', 'aac', '-b:a', '192k'])
        else:
            # 快速模式：-ss在-i前快速定位，然后重新编码确保可播放
            # 注意：即使是"快速"模式，也需要重新编码才能确保视频正确
            cmd.extend(['-ss', str(start_time), '-i', input_path])
            if end_time is not None:
                duration = end_time - start_time
                cmd.extend(['-t', str(duration)])
            # 使用fast preset平衡速度和质量
            cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-c:a', 'aac'])
        
        # 覆盖输出文件
        cmd.extend(['-y', output_path])
        
        print(f"正在剪辑视频...")
        print(f"输入: {input_path}")
        print(f"输出: {output_path}")
        print(f"开始时间: {start_time:.3f}s")
        if end_time:
            print(f"结束时间: {end_time:.3f}s")
        print(f"命令: {' '.join(cmd)}")  # 调试：显示完整命令
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                print(f"✓ 剪辑完成: {output_path}")
                return True
            else:
                print(f"✗ 剪辑失败:")
                print(result.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            print("✗ 剪辑超时")
            return False
        except Exception as e:
            print(f"✗ 剪辑过程中发生错误: {e}")
            return False
    
    def cut_before_timestamp(self,
                           input_path: str,
                           output_path: str,
                           cut_point: float,
                           reencode: bool = False) -> bool:
        """
        剪掉时间点之前的内容（保留时间点之后的内容）
        
        Args:
            input_path: 输入视频文件路径
            output_path: 输出视频文件路径
            cut_point: 剪切点时间（秒），该时间之前的内容会被剪掉
            reencode: 是否重新编码
            
        Returns:
            是否成功
        """
        return self.cut_from_timestamp(input_path, output_path, cut_point, None, reencode)
    
    def batch_cut_videos(self,
                        video_files: list,
                        timestamps: list,
                        output_dir: str,
                        suffix: str = '_cut',
                        reencode: bool = False) -> dict:
        """
        批量剪辑多个视频
        
        Args:
            video_files: 视频文件路径列表
            timestamps: 对应的剪切时间点列表
            output_dir: 输出目录
            suffix: 输出文件名后缀
            reencode: 是否重新编码
            
        Returns:
            结果字典 {视频路径: 是否成功}
        """
        if len(video_files) != len(timestamps):
            print("错误: 视频文件数量与时间戳数量不匹配")
            return {}
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        results = {}
        
        for video_path, timestamp in zip(video_files, timestamps):
            # 生成输出文件名
            base_name = Path(video_path).stem
            ext = Path(video_path).suffix
            output_name = f"{base_name}{suffix}{ext}"
            output_path = os.path.join(output_dir, output_name)
            
            print(f"\n处理: {video_path}")
            success = self.cut_before_timestamp(
                video_path,
                output_path,
                timestamp,
                reencode
            )
            
            results[video_path] = success
        
        # 打印总结
        print("\n" + "="*50)
        print("批量剪辑完成")
        success_count = sum(1 for v in results.values() if v)
        print(f"成功: {success_count}/{len(results)}")
        print("="*50)
        
        return results
    
    def cut_from_json(self,
                     json_path: str,
                     output_dir: Optional[str] = None,
                     suffix: str = '_cut',
                     reencode: bool = False) -> bool:
        """
        从JSON配置文件读取剪切信息并执行剪辑
        
        JSON格式示例:
        {
            "video_path": "video.mp4",
            "flash_timestamp": 2.5
        }
        
        或批量格式:
        [
            {"video_path": "video1.mp4", "flash_timestamp": 2.5},
            {"video_path": "video2.mp4", "flash_timestamp": 3.0}
        ]
        
        Args:
            json_path: JSON配置文件路径
            output_dir: 输出目录，None则使用视频所在目录
            suffix: 输出文件名后缀
            reencode: 是否重新编码
            
        Returns:
            是否成功
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"错误: 无法读取JSON文件: {e}")
            return False
        
        # 处理单个视频或批量视频
        if isinstance(data, dict):
            # 单个视频
            video_path = data.get('video_path')
            timestamp = data.get('flash_timestamp') or data.get('detection_time')
            
            if not video_path or timestamp is None:
                print("错误: JSON格式不正确，需要包含 'video_path' 和 'flash_timestamp'")
                return False
            
            # 确定输出路径
            if output_dir is None:
                output_dir = os.path.dirname(video_path) or '.'
            
            os.makedirs(output_dir, exist_ok=True)
            
            base_name = Path(video_path).stem
            ext = Path(video_path).suffix
            output_path = os.path.join(output_dir, f"{base_name}{suffix}{ext}")
            
            return self.cut_before_timestamp(video_path, output_path, timestamp, reencode)
        
        elif isinstance(data, list):
            # 批量视频
            video_files = [item.get('video_path') for item in data]
            timestamps = [item.get('flash_timestamp') or item.get('detection_time') for item in data]
            
            if output_dir is None:
                output_dir = './cut_output'
            
            results = self.batch_cut_videos(video_files, timestamps, output_dir, suffix, reencode)
            return all(results.values())
        
        else:
            print("错误: JSON格式不正确")
            return False


def quick_cut(video_path: str,
             cut_time: float,
             output_path: Optional[str] = None,
             reencode: bool = False) -> bool:
    """
    快速剪辑函数：剪掉指定时间点之前的内容
    
    Args:
        video_path: 视频文件路径
        cut_time: 剪切时间点（秒）
        output_path: 输出文件路径，None则自动生成
        reencode: 是否重新编码
        
    Returns:
        是否成功
    """
    cutter = VideoCutter()
    
    if output_path is None:
        base_name = Path(video_path).stem
        ext = Path(video_path).suffix
        output_path = f"{base_name}_cut{ext}"
    
    return cutter.cut_before_timestamp(video_path, output_path, cut_time, reencode)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  1. 直接剪辑: python video_cutter.py <视频文件> <开始时间(秒)> [输出文件]")
        print("  2. 从JSON剪辑: python video_cutter.py --json <JSON文件> [--output 输出目录]")
        print("\n示例:")
        print("  python video_cutter.py video.mp4 2.5")
        print("  python video_cutter.py video.mp4 2.5 output.mp4")
        print("  python video_cutter.py --json result.json --output ./cut_videos")
        sys.exit(1)
    
    if sys.argv[1] == '--json':
        # JSON模式
        if len(sys.argv) < 3:
            print("错误: 请指定JSON文件")
            sys.exit(1)
        
        json_path = sys.argv[2]
        output_dir = None
        
        if '--output' in sys.argv:
            idx = sys.argv.index('--output')
            if idx + 1 < len(sys.argv):
                output_dir = sys.argv[idx + 1]
        
        cutter = VideoCutter()
        success = cutter.cut_from_json(json_path, output_dir)
        
        sys.exit(0 if success else 1)
    
    else:
        # 直接剪辑模式
        video_path = sys.argv[1]
        
        if len(sys.argv) < 3:
            print("错误: 请指定开始时间（秒）")
            sys.exit(1)
        
        try:
            cut_time = float(sys.argv[2])
        except ValueError:
            print("错误: 时间必须是数字")
            sys.exit(1)
        
        output_path = sys.argv[3] if len(sys.argv) > 3 else None
        
        success = quick_cut(video_path, cut_time, output_path)
        
        sys.exit(0 if success else 1)
