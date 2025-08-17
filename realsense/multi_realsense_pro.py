"""Multi RealSense capture & pointcloud utilities.

This module provides:
 - get_realsense_id: list connected device serial numbers (sorted)
 - init_given_realsense: configure & start a pipeline (RGB + Depth optional)
 - SingleVisionProcess: separate process grabbing frames & (optionally) point cloud
 - MultiRealSense: helper orchestrating two cameras (front=master, right=slave) with sync.

Point cloud generation uses intrinsics; optional voxel (grid) sampling to downsample.

NOTE:
 Windows does not support the 'fork' start method; we fall back to 'spawn'.
 For hardware sync, connect the sync cable between cameras; master (sync_mode=1), slave (2).
"""

from multiprocessing import Process, Queue, get_start_method, set_start_method
import time
import numpy as np
import cv2
import pyrealsense2 as rs
from typing import List, Dict, Any, Optional

# ---------- Multiprocessing start method (safer cross‑platform) ----------
try:
    if get_start_method(allow_none=True) is None:
        # Prefer fork if available (Linux/macOS); else spawn (Windows)
        try:
            set_start_method("fork")
        except RuntimeError:
            set_start_method("spawn", force=True)
except Exception:
    pass

np.set_printoptions(precision=3, suppress=True)


# ---------- Device discovery & initialization ----------
def get_realsense_id() -> List[str]:
    ctx = rs.context()
    devices = ctx.query_devices()
    serials = [devices[i].get_info(rs.camera_info.serial_number) for i in range(len(devices))]
    serials.sort()
    print(f"Found {len(serials)} devices: {serials}")
    return serials


class CameraInfo:
    """Camera intrinsics for point cloud creation."""

    def __init__(self, width, height, fx, fy, cx, cy, scale=1.0):
        self.width = width
        self.height = height
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        self.scale = scale


def init_given_realsense(
    device: str,
    enable_rgb: bool = True,
    enable_depth: bool = False,
    enable_point_cloud: bool = False,  # kept for API consistency
    sync_mode: int = 0,
):
    """Initialize one RealSense device.

    sync_mode: 0 default, 1 master, 2 slave (applied to depth sensor if depth enabled)
    Returns: (pipeline, align, depth_scale, camera_info)
    """
    print(f"Initializing camera {device}")
    # We'll try multiple resolution combinations to avoid 'Couldn't resolve requests'
    depth_modes = [
        (640, 480),
        (848, 480),
        (1280, 720),
        (424, 240),
    ]
    color_modes = [
        (640, 480),
        (848, 480),
        (1280, 720),
        (640, 360),
        (1920, 1080),
    ]
    # If a user disables a stream, keep a single None candidate for simpler loop
    if not enable_depth:
        depth_modes = [None]
    if not enable_rgb:
        color_modes = [None]

    pipeline = rs.pipeline()
    chosen = None
    last_error = None
    for d_mode in depth_modes:
        for c_mode in color_modes:
            try:
                cfg = rs.config()
                cfg.enable_device(device)
                if d_mode is not None:
                    dw, dh = d_mode  # (w,h)
                    cfg.enable_stream(rs.stream.depth, dw, dh, rs.format.z16, 30)
                if c_mode is not None:
                    cw, ch = c_mode
                    cfg.enable_stream(rs.stream.color, cw, ch, rs.format.rgb8, 30)
                profile = pipeline.start(cfg)
                chosen = (d_mode, c_mode, profile)
                print(f"Started {device} with depth={d_mode} color={c_mode}")
                break
            except Exception as e:
                last_error = e
                try:
                    pipeline.stop()
                except Exception:
                    pass
                pipeline = rs.pipeline()
        if chosen is not None:
            break
    if chosen is None:
        raise RuntimeError(f"Failed to start device {device} with any supported combo: {last_error}")
    _, _, profile = chosen

    if enable_depth:
        device_obj = profile.get_device()
        # Usually depth sensor is the first returned sensor.
        depth_sensor = device_obj.first_depth_sensor()
        # Sync setting (requires Inter-Camera Sync cable installed)
        try:
            depth_sensor.set_option(rs.option.inter_cam_sync_mode, sync_mode)
            print(f"Set sync_mode={sync_mode} for {device}")
        except Exception as e:
            print(f"Warning: failed to set sync mode on {device}: {e}")

        # Minimum measurable distance
        try:
            depth_sensor.set_option(rs.option.min_distance, 0.05)
        except Exception:
            pass

        depth_scale = depth_sensor.get_depth_scale()
        align = rs.align(rs.stream.color)
        depth_profile = profile.get_stream(rs.stream.depth)
        intrinsics = depth_profile.as_video_stream_profile().get_intrinsics()
        print(
            f"Intrinsics({device}): w={intrinsics.width} h={intrinsics.height} fx={intrinsics.fx:.2f} fy={intrinsics.fy:.2f} "
            f"ppx={intrinsics.ppx:.2f} ppy={intrinsics.ppy:.2f} depth_scale={depth_scale}"
        )
        cam_info = CameraInfo(
            intrinsics.width,
            intrinsics.height,
            intrinsics.fx,
            intrinsics.fy,
            intrinsics.ppx,
            intrinsics.ppy,
            scale=1.0,  # we already multiply raw depth by depth_scale to get meters
        )
        print(f"camera {device} init.")
        return pipeline, align, depth_scale, cam_info
    else:
        print(f"camera {device} init.")
        return pipeline, None, None, None


# ---------- Point cloud helpers ----------
def grid_sample_pcd(point_cloud: np.ndarray, grid_size: float = 0.005):
    """Simple voxel (grid) sampling for point clouds (Keeps first point per voxel)."""
    if point_cloud.size == 0:
        return point_cloud
    coords = point_cloud[:, :3]
    scaled = np.floor(coords / grid_size).astype(np.int64)
    # Hash (avoid overflow using tuple conversion via structured array)
    keys = scaled[:, 0] + scaled[:, 1] * 73856093 + scaled[:, 2] * 19349663
    _, idx = np.unique(keys, return_index=True)
    return point_cloud[idx]


class SingleVisionProcess(Process):
    def __init__(
            self,
            device: str,
            queue: Queue,
            enable_rgb: bool = True,
            enable_depth: bool = False,
            enable_pointcloud: bool = False,
            sync_mode: int = 0,
            num_points: int = 2048,
            z_far: float = 1.0,
            z_near: float = 0.1,
            use_grid_sampling: bool = True,
            img_size: List[int] = [224, 224],
            apply_rotations: bool = True,
            apply_crop: bool = True,
            debug_pointcloud: bool = False,
            colorize_mode: str = "rgb",  # rgb | depth | height | xyz
        ) -> None:
        super().__init__()
        self.queue = queue
        self.device = device
        self.enable_rgb = enable_rgb
        self.enable_depth = enable_depth
        self.enable_pointcloud = enable_pointcloud
        self.sync_mode = sync_mode
        self.use_grid_sampling = use_grid_sampling
        self.resize = True
        self.height, self.width = img_size
        self.z_far = z_far
        self.z_near = z_near
        self.num_points = num_points
        self.pipeline = None
        self.align = None
        self.depth_scale = None
        self.camera_info = None  # type: Optional[CameraInfo]
        self._running = True
        self.apply_rotations = apply_rotations
        self.apply_crop = apply_crop
        self.debug_pointcloud = debug_pointcloud
        self.colorize_mode = colorize_mode.lower()

    # ---- Frame acquisition ----
    def get_vision(self):
        frame = self.pipeline.wait_for_frames()
        if self.enable_depth:
            aligned = self.align.process(frame)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            color = np.asanyarray(color_frame.get_data()) if self.enable_rgb else None
            depth = np.asanyarray(depth_frame.get_data()).astype(np.float32)
            depth *= self.depth_scale  # meters
            # Clip depth
            depth = np.clip(depth, 0.01, self.z_far)
            if self.enable_pointcloud and color is not None:
                pcd = self.create_colored_point_cloud(
                    color, depth, far=self.z_far, near=self.z_near, num_points=self.num_points
                )
            else:
                pcd = None
        else:
            color_frame = frame.get_color_frame()
            color = np.asanyarray(color_frame.get_data()) if self.enable_rgb else None
            depth = None
            pcd = None

        if self.resize and color is not None:
            color = cv2.resize(color, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        if self.resize and depth is not None:
            depth = cv2.resize(depth, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
        return color, depth, pcd

    def run(self):  # noqa: D401
        self.pipeline, self.align, self.depth_scale, self.camera_info = init_given_realsense(
            self.device,
            enable_rgb=self.enable_rgb,
            enable_depth=self.enable_depth,
            enable_point_cloud=self.enable_pointcloud,
            sync_mode=self.sync_mode,
        )
        while self._running:
            try:
                color, depth, pcd = self.get_vision()
                # Non-blocking put: drop oldest if queue full
                if self.queue.full():
                    try:
                        self.queue.get_nowait()
                    except Exception:
                        pass
                self.queue.put_nowait([color, depth, pcd])
            except Exception as e:
                print(f"Process {self.device} capture error: {e}")
                time.sleep(0.1)

    def terminate(self):  # graceful stop
        self._running = False
        try:
            if self.pipeline:
                self.pipeline.stop()
        except Exception:
            pass
        super().terminate()

    # ---- Geometry transforms ----
    def rotate_point_cloud(self, points, axis_point, axis_direction, angle_deg):
        angle_rad = np.deg2rad(angle_deg)
        axis_point = np.array(axis_point)
        axis_dir = np.array(axis_direction, dtype=np.float32)
        axis_dir /= (np.linalg.norm(axis_dir) + 1e-8)
        translated = points - axis_point
        ux, uy, uz = axis_dir
        c, s = np.cos(angle_rad), np.sin(angle_rad)
        R = np.array(
            [
                [c + ux * ux * (1 - c), ux * uy * (1 - c) - uz * s, ux * uz * (1 - c) + uy * s],
                [uy * ux * (1 - c) + uz * s, c + uy * uy * (1 - c), uy * uz * (1 - c) - ux * s],
                [uz * ux * (1 - c) - uy * s, uz * uy * (1 - c) + ux * s, c + uz * uz * (1 - c)],
            ]
        )
        rotated = translated @ R.T
        return rotated + axis_point

    # ---- Point cloud creation ----
    def create_colored_point_cloud(self, color, depth, far=1.0, near=0.1, num_points=10000):
        assert depth.shape[:2] == color.shape[:2]
        h, w = depth.shape
        xmap, ymap = np.meshgrid(np.arange(w), np.arange(h))
        z = depth / self.camera_info.scale
        x = (xmap - self.camera_info.cx) * z / self.camera_info.fx
        y = (ymap - self.camera_info.cy) * z / self.camera_info.fy
        cloud = np.stack([x, y, z], axis=-1).reshape(-1, 3)
        color_flat = color.reshape(-1, 3)
        mask = (cloud[:, 2] < far) & (cloud[:, 2] > near)
        cloud = cloud[mask]
        color_flat = color_flat[mask]
        original_count = cloud.shape[0]

        if self.apply_rotations:
            try:
                cloud = self.rotate_point_cloud(cloud, [0, 0.0080, 0.525], [0, 1, 0], 180)
                cloud = self.rotate_point_cloud(cloud, [-0.1156, -0.17, 0.3575], [1, 0, 0], -45)
                cloud = self.rotate_point_cloud(cloud, [0.0141, -0.181, 0], [0, 0, 1], -15)
            except Exception:
                if self.debug_pointcloud:
                    print("Rotation step failed; continuing without rotations.")

        if self.apply_crop:
            mask2 = (cloud[:, 0] > -0.3) & (cloud[:, 0] < 0.25) & (cloud[:, 1] < 0.01) & (cloud[:, 1] > -0.4)
            cloud = cloud[mask2]
            color_flat = color_flat[mask2]

        if self.debug_pointcloud:
            print(
                f"[PCD Debug {self.device}] after depth-filter={original_count} final={cloud.shape[0]} "
                f"rot={'on' if self.apply_rotations else 'off'} crop={'on' if self.apply_crop else 'off'}"
            )

        # Re-color based on mode if requested
        if cloud.shape[0] > 0 and self.colorize_mode != "rgb":
            try:
                if self.colorize_mode in ("depth", "z"):
                    vals = cloud[:, 2]
                elif self.colorize_mode == "height":
                    vals = cloud[:, 1]
                elif self.colorize_mode == "xyz":
                    # Normalize each axis then combine
                    mn = cloud.min(axis=0)
                    mx = cloud.max(axis=0)
                    rng = (mx - mn) + 1e-8
                    norm = (cloud - mn) / rng
                    color_flat = (norm * 255).astype(np.float32)
                    vals = None  # Already assigned
                else:
                    vals = None
                if vals is not None:
                    vmin, vmax = vals.min(), vals.max()
                    scale = (vals - vmin) / (vmax - vmin + 1e-8)
                    # Use matplotlib turbo (fallback to viridis) without global import cost
                    try:
                        import matplotlib.cm as cm
                        cmap = cm.get_cmap('turbo')
                    except Exception:
                        import matplotlib.cm as cm
                        cmap = cm.get_cmap('viridis')
                    mapped = cmap(scale)[:, :3] * 255.0
                    color_flat = mapped.astype(np.float32)
            except Exception as e:
                if self.debug_pointcloud:
                    print(f"Colorize mode '{self.colorize_mode}' failed: {e}; fallback to original RGB.")

        colored_cloud = np.hstack([cloud, color_flat.astype(np.float32)])
        if self.use_grid_sampling and colored_cloud.shape[0] > 0:
            colored_cloud = grid_sample_pcd(colored_cloud, grid_size=0.005)

        if colored_cloud.shape[0] == 0:
            # No valid points; return a single dummy point to avoid empty arrays
            return np.zeros((num_points, 6), dtype=np.float32)

        if num_points > colored_cloud.shape[0]:
            # Instead of zero padding (would collapse to a dot), repeat existing points
            repeat_idx = np.random.choice(colored_cloud.shape[0], num_points - colored_cloud.shape[0], replace=True)
            colored_cloud = np.concatenate([colored_cloud, colored_cloud[repeat_idx]], axis=0)
        else:
            sel = np.random.choice(colored_cloud.shape[0], num_points, replace=False)
            colored_cloud = colored_cloud[sel]
        np.random.shuffle(colored_cloud)
        return colored_cloud


# ---------- Multi camera orchestrator ----------
class MultiRealSense:
    def __init__(
        self,
        use_front_cam: bool = True,
        use_right_cam: bool = True,
        front_num_points: int = 4096,
        right_num_points: int = 4096,
        front_z_far: float = 1.5,
        front_z_near: float = 0.25,
        right_z_far: float = 1.5,
        right_z_near: float = 0.25,
        use_grid_sampling: bool = True,
        img_size: List[int] = [384, 384],
    apply_rotations: bool = True,
    apply_crop: bool = True,
    debug_pointcloud: bool = False,
    colorize_mode: str = "rgb",
    ):
        self.devices = get_realsense_id()
        if len(self.devices) < (1 if use_front_cam or use_right_cam else 0) + (1 if use_right_cam and use_front_cam else 0):
            print("Warning: Not enough devices detected for requested configuration.")

        self.use_front_cam = use_front_cam and len(self.devices) >= 1
        self.use_right_cam = use_right_cam and len(self.devices) >= 2

        self.front_queue = Queue(maxsize=3)
        self.right_queue = Queue(maxsize=3)

        self.front_proc: Optional[SingleVisionProcess] = None
        self.right_proc: Optional[SingleVisionProcess] = None

        # Assign serials deterministically
        if self.use_front_cam:
            front_serial = self.devices[0]
            self.front_proc = SingleVisionProcess(
                device=front_serial,
                queue=self.front_queue,
                enable_rgb=True,
                enable_depth=True,
                enable_pointcloud=True,
                sync_mode=1,  # master
                num_points=front_num_points,
                z_far=front_z_far,
                z_near=front_z_near,
                use_grid_sampling=use_grid_sampling,
                img_size=img_size,
                apply_rotations=apply_rotations,
                apply_crop=apply_crop,
                debug_pointcloud=debug_pointcloud,
                colorize_mode=colorize_mode,
            )
            self.front_proc.start()
            print(f"Started front camera (master) {front_serial}")

        if self.use_right_cam:
            right_serial = self.devices[1]
            self.right_proc = SingleVisionProcess(
                device=right_serial,
                queue=self.right_queue,
                enable_rgb=True,
                enable_depth=True,
                enable_pointcloud=True,
                sync_mode=2,  # slave
                num_points=right_num_points,
                z_far=right_z_far,
                z_near=right_z_near,
                use_grid_sampling=use_grid_sampling,
                img_size=img_size,
                apply_rotations=apply_rotations,
                apply_crop=apply_crop,
                debug_pointcloud=debug_pointcloud,
                colorize_mode=colorize_mode,
            )
            self.right_proc.start()
            print(f"Started right camera (slave) {right_serial}")

    def _drain_latest(self, q: Queue):
        last = None
        while not q.empty():
            last = q.get()
        return last

    def __call__(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.use_front_cam:
            v = self._drain_latest(self.front_queue)
            if v is not None:
                out["front_color"], out["front_depth"], out["front_point_cloud"] = v
        if self.use_right_cam:
            v = self._drain_latest(self.right_queue)
            if v is not None:
                out["right_color"], out["right_depth"], out["right_point_cloud"] = v
        # Combined point cloud (simple concat) if both available
        if "front_point_cloud" in out and "right_point_cloud" in out:
            if out["front_point_cloud"] is not None and out["right_point_cloud"] is not None:
                out["merged_point_cloud"] = np.vstack([out["front_point_cloud"], out["right_point_cloud"]])
        return out

    def finalize(self):
        if self.front_proc is not None:
            self.front_proc.terminate()
            self.front_proc.join(timeout=2)
            self.front_proc = None
        if self.right_proc is not None:
            self.right_proc.terminate()
            self.right_proc.join(timeout=2)
            self.right_proc = None

    def __del__(self):
        try:
            self.finalize()
        except Exception:
            pass


if __name__ == "__main__":
    """Quick manual test: capture a few frames then exit."""
    from pointcloud import visualize_pointcloud

    multi = MultiRealSense(use_front_cam=True, use_right_cam=True)
    try:
        for i in range(10):
            data = multi()
            if "merged_point_cloud" in data:
                print(
                    f"Frame {i}: front_color={None if 'front_color' not in data else data['front_color'].shape} "
                    f"merged_pcd={data['merged_point_cloud'].shape}"
                )
                # Visualize only first successful frame to avoid multiple Flask servers
                visualize_pointcloud(data["merged_point_cloud"])
                break
            time.sleep(0.1)
    finally:
        multi.finalize()