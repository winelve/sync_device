# -*- coding: utf-8 -*-
"""
A minimal, high-performance RealSense D405 recorder using pyrealsense2.
- Simple API: start(path), stop()
- Defaults tailored for D405 (depth 640x480 @ 30fps)
- Writes RealSense .bag files (lossless, with full metadata)
- Safely drains frames in a lightweight background thread to avoid internal queue back-pressure

Usage:
    from d405_recorder import D405Recorder

    rec = D405Recorder(fps=30)  # width=640, height=480 by default
    rec.start("output/session01.bag")
    # ... do other work ...
    rec.stop()

CLI:
    python d405_recorder.py --path output/session01.bag --fps 30
"""

# -*- coding: utf-8 -*-
"""
RealSense 录制器（优先针对 D405，但可自动探测并录制彩色流）
- 简洁 API：start(path), stop()
- 默认录制深度到 .bag；若设备支持 RGB，则可同时录制 color
- 轻量后台线程持续取帧，避免队列背压

用法：
    from d405_recorder import D405Recorder
    rec = D405Recorder(record_color=True)  # 如设备有 RGB，会自动一起录
    rec.start("output/session01.bag")
    rec.stop()
"""

import time
import threading
from pathlib import Path
from typing import Optional, List, Tuple
import sys

try:
    import pyrealsense2 as rs
except ImportError as e:
    raise ImportError("pyrealsense2 is required. Install with: pip install pyrealsense2") from e


class D405Recorder:
    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        serial: Optional[str] = None,
        device_name_hint: str = "D405",  # 如设为 None，将不按名称过滤，选第一个设备
        overwrite: bool = False,
        record_color: bool = True,       # 自动探测并尝试录制彩色（若设备支持）
        color_width: Optional[int] = None,
        color_height: Optional[int] = None,
        color_fps: Optional[int] = None,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)

        self.serial = serial
        self.device_name_hint = device_name_hint or ""
        self.overwrite = overwrite

        self.record_color = record_color
        self.color_width = int(color_width) if color_width else None
        self.color_height = int(color_height) if color_height else None
        self.color_fps = int(color_fps) if color_fps else None

        self._pipeline: Optional[rs.pipeline] = None
        self._pipeline_profile: Optional[rs.pipeline_profile] = None
        self._record_path: Optional[Path] = None
        self._drain_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frames_seen = 0
        self._is_recording = False

    @staticmethod
    def list_devices() -> List[Tuple[str, str]]:
        ctx = rs.context()
        out = []
        for dev in ctx.query_devices():
            out.append((
                dev.get_info(rs.camera_info.serial_number),
                dev.get_info(rs.camera_info.name),
            ))
        return out

    def _select_device(self) -> Tuple[str, str]:
        ctx = rs.context()
        candidates = []
        for dev in ctx.query_devices():
            serial = dev.get_info(rs.camera_info.serial_number)
            name = dev.get_info(rs.camera_info.name)
            if self.serial:
                if serial == self.serial:
                    return serial, name
            else:
                if (self.device_name_hint.lower() in name.lower()) or (not self.device_name_hint):
                    candidates.append((serial, name))

        if self.serial:
            raise RuntimeError(f"未找到指定序列号的设备: {self.serial}")

        if not candidates:
            all_devs = ", ".join([f"{s} ({n})" for s, n in self.list_devices()]) or "无"
            hint = f"（名称包含 '{self.device_name_hint}'）" if self.device_name_hint else ""
            raise RuntimeError(f"未找到设备{hint}。当前设备: {all_devs}")

        return candidates[0]

    def _prepare_path(self, path: str) -> Path:
        p = Path(path)
        if p.suffix.lower() != ".bag":
            p = p.with_suffix(".bag")
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not self.overwrite:
            raise FileExistsError(f"录制文件已存在: {p}（如需覆盖，初始化时设置 overwrite=True）")
        return p

    def _can_resolve(self, serial: str, streams: List[Tuple]):
        """
        检查 streams 组合是否可用。
        streams 中的元素形如: (rs.stream.depth, w, h, rs.format.z16, fps)
        """
        try:
            test_cfg = rs.config()
            test_cfg.enable_device(serial)
            for (st, w, h, fmt, f) in streams:
                test_cfg.enable_stream(st, int(w), int(h), fmt, int(f))
            wrapper = rs.pipeline_wrapper(self._pipeline)
            return test_cfg.can_resolve(wrapper)
        except Exception:
            return False

    def _choose_streams(self, serial: str) -> List[Tuple]:
        streams = [(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)]
        if self.record_color:
            cw = self.color_width or self.width
            ch = self.color_height or self.height
            cf = self.color_fps or self.fps
            candidate = streams + [(rs.stream.color, cw, ch, rs.format.rgb8, cf)]
            if self._can_resolve(serial, candidate):
                return candidate
            # 尝试一次常见 fallback（848x480 @ fps）
            fallback = streams + [(rs.stream.color, 848, 480, rs.format.rgb8, cf)]
            if self._can_resolve(serial, fallback):
                return fallback
            # 放弃彩色
        return streams

    def _drain_loop(self):
        try:
            while not self._stop_event.is_set():
                if not self._pipeline:
                    break
                frames = self._pipeline.poll_for_frames()  # 非阻塞获取
                if frames:
                    self._frames_seen += 1
                else:
                    time.sleep(0.002)
        except Exception:
            pass

    def start(self, path: str):
        if self._is_recording:
            raise RuntimeError("录制已在进行中。请先调用 stop()。")

        serial, name = self._select_device()
        self._record_path = self._prepare_path(path)

        self._pipeline = rs.pipeline()
        config = rs.config()
        config.enable_device(serial)

        # 选择可用的流组合（深度必选，彩色按可用性启用）
        streams = self._choose_streams(serial)
        for (st, w, h, fmt, f) in streams:
            config.enable_stream(st, int(w), int(h), fmt, int(f))

        # 直接由 SDK 录制到 .bag
        config.enable_record_to_file(str(self._record_path))

        # 启动
        self._pipeline_profile = self._pipeline.start(config)

        # 可选：设置为高精度预设（若支持）
        try:
            dev = self._pipeline_profile.get_device()
            depth_sensor = dev.first_depth_sensor()
            if depth_sensor.supports(rs.option.visual_preset):
                depth_sensor.set_option(rs.option.visual_preset, 3)  # High Accuracy
        except Exception:
            pass

        # 启动排水线程
        self._stop_event.clear()
        self._frames_seen = 0
        self._drain_thread = threading.Thread(target=self._drain_loop, name="RSDrain", daemon=True)
        self._drain_thread.start()

        self._is_recording = True

        # 简要提示已启用的流
        enabled = []
        for (st, w, h, _, f) in streams:
            enabled.append(f"{st.name} {w}x{h}@{f}")
        print(f"[D405Recorder] 设备: {name} ({serial})，记录: {', '.join(enabled)} -> {self._record_path}")

    def stop(self):
        if not self._is_recording:
            return
        self._stop_event.set()
        if self._drain_thread and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=2.0)
        self._drain_thread = None
        try:
            if self._pipeline:
                self._pipeline.stop()
        finally:
            self._pipeline = None
            self._pipeline_profile = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def record_path(self) -> Optional[str]:
        return str(self._record_path) if self._record_path else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

def _parse_args(argv: List[str]):
    import argparse

    parser = argparse.ArgumentParser(description="RealSense D405 录制器（.bag）")
    parser.add_argument("--path", type=str, required=True, help="输出 .bag 文件路径（自动补全 .bag 后缀）")
    parser.add_argument("--width", type=int, default=640, help="深度宽度 (默认 640)")
    parser.add_argument("--height", type=int, default=480, help="深度高度 (默认 480)")
    parser.add_argument("--fps", type=int, default=30, help="帧率 (默认 30)")
    parser.add_argument("--serial", type=str, default=None, help="指定相机序列号（可选）")
    parser.add_argument("--overwrite", action="store_true", help="若目标文件存在则覆盖")
    return parser.parse_args(argv)


def _main(argv: List[str]) -> int:
    args = _parse_args(argv)
    rec = D405Recorder(
        width=args.width,
        height=args.height,
        fps=args.fps,
        serial=args.serial,
        overwrite=args.overwrite,
    )
    try:
        rec.start(args.path)
        print(f"[D405Recorder] 正在录制到: {rec.record_path}")
        print("[D405Recorder] 按 Ctrl+C 结束录制...")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[D405Recorder] 停止录制...")
    except Exception as e:
        print(f"[D405Recorder] 错误: {e}", file=sys.stderr)
        return 1
    finally:
        rec.stop()
        print("[D405Recorder] 已保存并释放资源。")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))