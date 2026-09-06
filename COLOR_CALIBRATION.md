# 桌宠色彩校准说明

## 问题

当前插件桌宠截图与 EAC 原生参考图相比，整体亮度和暖色分量略高：
- 原图均值：R 67.55 / G 72.47 / B 92.78
- 参考均值：R 65.37 / G 70.43 / B 89.83
- 原图偏亮，且暗部背景、皮肤、扫帚等区域的暖橙分量更明显。

## 校准方法

使用逐通道均值/标准差匹配（白平衡 + 亮度校准）：

`out = clip(gain * src + offset)`

实际参数：

| 通道 | gain | offset |
|---|---:|---:|
| R | 1.0107 | -2.907 |
| G | 1.0148 | -3.107 |
| B | 1.0066 | -3.567 |

该变换在保持细节和明暗层次的同时，将整体色温拉回 EAC 原生的冷蓝调。

## 使用方法

```powershell
py -3 scripts/calibrate-color.py <source.png> <reference.png> <output.png>
```

## 输出文件

- `docs/color-calibration-comparison.png`：校准前/后对比图。
- `docs/calibrated-pet.png`：校准后的结果图（如需交付图片）。
