"""
视频亮度变化检测模块
支持: mp4/avi/mov/mkv(Kinect)/bag(RealSense)
"""

import cv2
import numpy as np
from typing import Optional, Tuple, List
import json
import os


class VideoReader:
    """统一视频读取器，支持多种格式"""
    
    def __init__(self, path: str):
        self.path = path
        self.cap = None
        self.pipeline = None
        self.is_realsense = path.endswith('.bag')
        
        if self.is_realsense:
            try:
                import pyrealsense2 as rs
                self.pipeline = rs.pipeline()
                config = rs.config()
                config.enable_device_from_file(path, repeat_playback=False)
                config.enable_stream(rs.stream.color)
                self.pipeline.start(config)
            except ImportError:
                raise ImportError("需要安装: pip install pyrealsense2")
            except Exception as e:
                raise IOError(f"无法打开bag文件: {e}")
        else:
            # 支持mp4/avi/mov/mkv(Kinect)
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened():
                raise IOError(f"无法打开视频: {path}")
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.is_realsense:
            try:
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                color = frames.get_color_frame()
                return (True, np.asanyarray(color.get_data())) if color else (False, None)
            except:
                return False, None
        return self.cap.read()
    
    def get(self, prop):
        if self.is_realsense:
            return 30.0 if prop == cv2.CAP_PROP_FPS else 9999
        return self.cap.get(prop)
    
    def set(self, prop, val):
        return self.cap.set(prop, val) if not self.is_realsense else False
    
    def release(self):
        if self.is_realsense and self.pipeline:
            self.pipeline.stop()
        elif self.cap:
            self.cap.release()
    
    def isOpened(self):
        return self.pipeline is not None if self.is_realsense else (self.cap and self.cap.isOpened())


class BrightnessChangeDetector:
    """检测视频亮度变化"""
    
    def __init__(self, sensitivity: float = 0.3):
        """
        初始化检测器
        
        Args:
            sensitivity: 灵敏度(0-1)，越小越灵敏
                        0.1 = 非常灵敏（变化10%就触发）
                        0.3 = 标准灵敏度（变化30%触发）
                        0.5 = 不灵敏（变化50%才触发）
        """
        self.sensitivity = sensitivity
    
    def _get_brightness(self, frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]] = None) -> float:
        """计算帧亮度"""
        if roi:
            x, y, w, h = roi
            frame = frame[y:y+h, x:x+w]
        return np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    
    def _find_roi(self, path: str, samples: int = 30) -> Optional[Tuple[int, int, int, int]]:
        """自动检测最亮区域"""
        cap = VideoReader(path)
        if not cap.isOpened():
            return None
        
        max_map = None
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, count // samples)
        
        for i in range(0, count, step):
            if not cap.is_realsense:
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret or max_map is not None and len(max_map) >= samples:
                break
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            max_map = gray if max_map is None else np.maximum(max_map, gray)
        
        cap.release()
        
        if max_map is None:
            return None
        
        _, thresh = cv2.threshold(max_map.astype(np.uint8), 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
        return (max(0, x-20), max(0, y-20), w+40, h+40)  # 加边距
    
    def detect(self, path: str, roi: Optional[Tuple] = None, viz: bool = False, 
               save: bool = False, save_path: str = None) -> Optional[Tuple[float, int]]:
        """
        检测闪光时刻
        
        Args:
            path: 视频路径(mp4/avi/mov/mkv/bag)
            roi: ROI区域(x,y,w,h)，None=自动检测
            viz: 是否显示图表
            save: 是否保存图表
            save_path: 保存路径
            
        Returns:
            (时间戳(秒), 帧号) 或 None
        """
        cap = VideoReader(path)
        if not cap.isOpened():
            print(f"错误: 无法打开 {path}")
            return None
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"FPS: {fps:.1f}")
        
        # ROI检测
        if roi is None:
            print("自动检测ROI...")
            roi = self._find_roi(path)
            if roi:
                print(f"ROI: {roi}")
        
        # 收集亮度
        brightness, frames = [], []
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            brightness.append(self._get_brightness(frame, roi))
            frames.append(idx)
            idx += 1
            if idx % 100 == 0:
                print(f"处理: {idx} 帧")
        
        cap.release()
        
        if not brightness:
            return None
        
        # 分析
        frame_num = self._analyze(brightness, frames)
        if frame_num is None:
            return None
        
        timestamp = frame_num / fps
        print(f"检测: 帧{frame_num}, {timestamp:.3f}秒")
        
        # 可视化
        if viz or save:
            self._plot(brightness, frames, frame_num, fps, viz, save, save_path or path)
        
        return (timestamp, frame_num)
    
    def _analyze(self, brightness: List[float], frames: List[int]) -> Optional[int]:
        """分析亮度，找突变点"""
        arr = np.array(brightness)
        win = min(5, len(arr) // 10) if len(arr) >= 20 else 2
        smoothed = np.convolve(arr, np.ones(win)/win, mode='valid')
        
        # 计算基线（前10%的平均亮度）
        base_len = max(10, len(smoothed) // 10)
        baseline = np.mean(smoothed[:base_len])
        
        # 计算阈值：baseline × (1 + sensitivity)
        # 例如：baseline=120, sensitivity=0.3 → threshold=156
        # 当亮度从120变到156时触发（变化了30%）
        threshold = baseline * (1 + self.sensitivity)
        
        print(f"基线亮度: {baseline:.1f}, 触发阈值: {threshold:.1f} (需变化 {self.sensitivity*100:.0f}%)")
        
        # 扫描：找第一次超过阈值的点（上升）或低于下限的点（下降）
        lower_threshold = baseline * (1 - self.sensitivity)
        
        for i in range(base_len, len(smoothed)):
            # 检测上升或下降
            if smoothed[i] > threshold or smoothed[i] < lower_threshold:
                change_pct = abs(smoothed[i] - baseline) / baseline * 100
                direction = "上升" if smoothed[i] > baseline else "下降"
                print(f"检测到{direction}: {baseline:.1f} → {smoothed[i]:.1f} (变化 {change_pct:.1f}%)")
                return frames[i]
        
        # 后备方案：使用最大梯度点
        grad = np.abs(np.diff(smoothed))
        idx = np.argmax(grad)
        print(f"未找到明显变化，使用最大梯度点")
        return frames[idx] if idx < len(frames) else None
    
    def _plot(self, brightness: List, frames: List, trans: int, fps: float,
              show: bool, save: bool, path: str):
        """绘制亮度曲线"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            if not show:
                matplotlib.use('Agg')
            
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            times = [f / fps for f in frames]
            trans_time = trans / fps
            
            plt.figure(figsize=(12, 6))
            plt.plot(times, brightness, linewidth=1, label='亮度')
            plt.axvline(trans_time, color='r', linestyle='--', label=f'检测点({trans_time:.3f}s)')
            plt.xlabel('时间(秒)')
            plt.ylabel('亮度值')
            plt.title('视频亮度变化分析')
            plt.legend()
            plt.grid(alpha=0.3)
            plt.tight_layout()
            
            if save:
                from pathlib import Path
                if not path.endswith('.png'):
                    path = f"{Path(path).stem}_brightness.png"
                os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
                plt.savefig(path, dpi=150, bbox_inches='tight')
                print(f"图表: {path}")
            
            if show:
                plt.show()
            else:
                plt.close()
        except ImportError:
            print("需要matplotlib: pip install matplotlib")


# ============ 简化接口 ============

def detect_flash(video_path: str, config: dict = None) -> Optional[Tuple[float, int]]:
    """
    检测闪光（简化接口）
    
    Args:
        video_path: 视频路径(mp4/avi/mov/mkv/bag)
        config: 配置字典
        
    Returns:
        (时间戳(秒), 帧号) 或 None
    """
    cfg = config or {}
    det = cfg.get('detection', {})
    viz = cfg.get('visualization', {})
    
    detector = BrightnessChangeDetector(
        sensitivity=det.get('sensitivity', 0.3)
    )
    
    return detector.detect(
        video_path,
        viz=viz.get('enable', False),
        save=viz.get('save_plot', False),
        save_path=viz.get('plot_dir')
    )


def detect_and_save(video_path: str, output_json: str = None, 
                    visualize: bool = False) -> Optional[Tuple[float, int]]:
    """
    检测并保存结果（兼容旧接口）
    
    Args:
        video_path: 视频路径
        output_json: JSON输出路径
        visualize: 是否可视化
        
    Returns:
        (时间戳(秒), 帧号) 或 None
    """
    detector = BrightnessChangeDetector()
    result = detector.detect(video_path, viz=visualize)
    
    if result and output_json:
        data = {
            'video_path': video_path,
            'flash_timestamp': result[0],
            'flash_frame': result[1]
        }
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"保存: {output_json}")
    
    return result


# ============ 命令行 ============

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python capture.py <视频> [--visualize] [--output result.json]")
        print("支持: mp4/avi/mov/mkv(Kinect)/bag(RealSense)")
        sys.exit(1)
    
    path = sys.argv[1]
    viz = '--visualize' in sys.argv
    out = sys.argv[sys.argv.index('--output') + 1] if '--output' in sys.argv else None
    
    result = detect_and_save(path, out, viz)
    
    if result:
        print(f"\n✓ 成功: {result[0]:.3f}秒 (帧{result[1]})")
    else:
        print("\n✗ 未检测到闪光")
