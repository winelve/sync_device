import open3d as o3d
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
            vis = o3d.visualization.VisualizerWithKeyCallback()
            vis.create_window(window_name="Open3D Point Cloud Viewer", width=1200, height=800)
            vis.add_geometry(pcd)
            opt = vis.get_render_option()
            opt.point_size = 3  # 初始点大小

            def increase_point_size(vis):
                opt.point_size += 1
                print(f"Point size: {opt.point_size}")
                return False

            def decrease_point_size(vis):
                opt.point_size = max(1, opt.point_size - 1)
                print(f"Point size: {opt.point_size}")
                return False

            vis.register_key_callback(ord('+'), increase_point_size)
            vis.register_key_callback(ord('-'), decrease_point_size)
            vis.run()
            vis.destroy_window()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    file_path = "D:\\code\\python\\sync_device\\output\\point_cloud\\v5\\output_frame_0004.ply"
    view_ply(file_path)