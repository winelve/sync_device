"""Dual RealSense cameras capture & merged point cloud visualization.

Usage:
	python multi.py
"""

import time
from multi_realsense_pro import MultiRealSense
from pointcloud import visualize_pointcloud


def main():
	cam = MultiRealSense(use_front_cam=True, use_right_cam=True)
	try:
		for i in range(200):
			data = cam()
			if "merged_point_cloud" in data:
				print(
					f"Merged PCD frame {i}: {data['merged_point_cloud'].shape} "
					f"front={None if 'front_point_cloud' not in data else data['front_point_cloud'].shape} "
					f"right={None if 'right_point_cloud' not in data else data['right_point_cloud'].shape}"
				)
				visualize_pointcloud(data["merged_point_cloud"])
				break
			time.sleep(0.1)
	finally:
		cam.finalize()


if __name__ == "__main__":
	main()

