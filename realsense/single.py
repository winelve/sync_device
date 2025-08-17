"""Single RealSense camera capture & visualization.

Usage (PowerShell):
	python single.py

Opens a Flask window (blocking) for point cloud. Captures frames until a
valid point cloud is obtained then visualizes & exits.
"""

import time
from multi_realsense_pro import MultiRealSense
from pointcloud import visualize_pointcloud


def main():
	# Disable rotations & crop first to debug collapsed point cloud; enable debug logs
	cam = MultiRealSense(use_front_cam=True, use_right_cam=False,
		apply_rotations=False, apply_crop=False, debug_pointcloud=True, colorize_mode="depth")
	try:
		for i in range(100):
			data = cam()
			if "front_point_cloud" in data and data["front_point_cloud"] is not None:
				print(f"Got point cloud frame {i}: {data['front_point_cloud'].shape}")
				visualize_pointcloud(data["front_point_cloud"])
				break
			time.sleep(0.1)
	finally:
		cam.finalize()


if __name__ == "__main__":
	main()

