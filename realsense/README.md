## RealSense 多相机点云可视化使用指南

### 1. 基本脚本
单帧/非实时：
- `single.py` 获取单个相机点云并一次性可视化（Flask 打开后结束采集）。
- `multi.py` 获取双相机并合并点云一次性展示。

实时轮询展示：
- `realtime_flask.py` 后台线程持续采集，前端定时 fetch 更新 Plotly。

### 2. 运行环境依赖
```
pip install pyrealsense2 numpy opencv-python flask plotly matplotlib
```
（可选保存静态图：`pip install kaleido`）

### 3. 实时脚本核心参数（`realtime_flask.py`）

| 参数 | 说明 | 建议范围/示例 |
|------|------|---------------|
| `--dual` | 启用第二个相机并采集合并点云 | 插上两台相机再加此参数 |
| `--view` | 双相机显示模式：`merged` 合并 / `separate` 左右分屏 | `--dual --view separate` |
| `--interval` | 浏览器轮询刷新间隔（毫秒）| 400~1000（太低占 CPU/网络） |
| `--capture-interval` | 后台采集线程间隔（毫秒） | 50~150 |
| `--max-points` | 发送到前端的点数上限（随机下采样） | 5k~20k |
| `--colorize` | 颜色模式：`rgb` / `depth` / `height` / `xyz` | 深度：`depth` |
| `--orient` | 坐标系调整：`default` / `swap_yz` / `y_up` / `camera_to_zup` | 推荐 `camera_to_zup` |

### 4. 常用命令示例
单相机（深度伪彩 + z 轴向上转换 + 中等刷新）：
```
python realtime_flask.py --interval 600 --capture-interval 120 --colorize depth --orient camera_to_zup
```
双相机合并点云（XYZ 归一伪彩，下采样到 8000 点）：
```
python realtime_flask.py --dual --interval 800 --capture-interval 150 --colorize xyz --max-points 8000
```
双相机分屏分别显示：
```
python realtime_flask.py --dual --view separate --interval 700 --colorize depth
```

### 5. 前端交互

- Pause / Resume：暂停或恢复自动刷新（空格键快捷键）。
- Step：暂停状态下单步抓取一帧（便于观察细节）。
- 分屏模式：`front`、`right` 两个独立 Plotly 视窗。

### 6. 坐标系说明
RealSense 原始：x=右, y=下, z=前。
`--orient camera_to_zup` 转换：Xw = z, Yw = x, Zw = -y（右手系，z 向上）。
如果想要自定义旋转矩阵，可后续加一个 `--extrinsic <file>` 载入 4x4 变换。

### 7. 颜色模式说明
- rgb：使用传感器彩色图对应的 RGB（对齐深度后形成点云）。
- depth(z)：按 z（深度）线性归一映射 turbo colormap。
- height(y)：按 y（高度/垂直轴）着色（配合 `--orient camera_to_zup` 更直观）。
- xyz：对 x,y,z 各自归一后直接作为 R,G,B（局部结构对比明显）。

### 8. 性能优化建议
- 减少 `--interval` 频率或提高它（例如 800ms）减轻浏览器压力。
- 调低 `--max-points`（如 6000）+ 后端 voxel 下采样（可在采集进程中添加）。
- 双相机合并后点数翻倍，可以对每个相机先独立随机采样再拼接。

### 9. 扩展点（可按需实现）
- WebSocket / SSE 降低轮询开销。
- 点云导出按钮（PLY / NPZ）。
- 外参标定矩阵加载，真实空间对齐合并双机点云。
- 自定义裁剪/ROI 过滤参数（深度范围、盒子裁剪）。

### 10. 常见问题
1. 只有一个黑点：可能是点云被裁剪或所有点重合，检查 `apply_crop`、`apply_rotations` 是否关闭测试。
2. 深度全灰：场景太近或太远，调整 `z_near` / `z_far`。
3. 想暂停观察细节：用页面 Pause 按钮或空格，再用 Step 单帧推进。

---
如需添加“保存当前帧”或“外参对齐”，继续指出即可。