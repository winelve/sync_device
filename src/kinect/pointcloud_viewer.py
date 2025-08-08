import open3d as o3d
import sys
import os

def view_ply(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return
    if not file_path.lower().endswith('.ply'):
        print(f"Error: File '{file_path}' is not a PLY file.")
        return
    try:
        pcd = o3d.io.read_point_cloud(file_path)
        if pcd.is_empty():
            print("Point cloud is empty.")
        else:
            print(f"Successfully loaded point cloud from '{file_path}'.")
            o3d.visualization.draw_geometries([pcd])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    file_path = "D:\code\python\sync_device\output\point_cloud\\v5\output_frame_0004.ply"
    view_ply(file_path)