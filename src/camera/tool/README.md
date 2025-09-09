# PlyPointCloud 的使用方法

`PlyPointCloud 包含深度数据的视频.mkv 输出文件夹 [--depth|--rgb]`

```shell
参数:
--depth: 将深度值映射成颜色

使用 HSV 色彩空间创建彩虹映射
近距离：红色 (小深度值)
中距离：黄色、绿色
远距离：蓝色 (大深度值)

--rgb: 将rgb数据映射到点云图上

默认是 --depth

例子:
PlyPointCloud vedio.mkv ./out      # 默认是depth
PlyPointCloud vedio.mkv ./out --depth
PlyPointCloud vedio.mkv ./out --rgb
```







