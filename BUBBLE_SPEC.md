# EAC 原生聊天气泡复用说明

## 1. 图片来源分析

参考图右侧为 EAC 原版气泡，左侧为此前自定义云朵气泡。对比后目标改为：**直接复用 EAC 原版样式，不做重新设计。**

## 2. 复用来源

- 历史来源：`%USERPROFILE%\.dsh\profiles\web-desktop\node_modules\dsh-dafeiyu\runtime\helper.py`
- 复刻内容：卡片尺寸、双层阴影、大圆角、半透明描边、标题/副标题字体、右侧状态圆点及不同状态图标。
- 许可证：使用本地已安装插件源码，仅在本机插件内复刻视觉参数，不引入新外部素材。

## 3. 原生视觉规格

| 项目 | 规格 |
|---|---|
| 窗口 | 宽 448px（按文字加宽），高 98px |
| 卡片 | x=14，y=7，宽=窗口宽-28，高=84 |
| 圆角 | 30px |
| 阴影 | 两层：`rgba(17,24,39,13)` 偏移 (1,13)；`rgba(17,24,39,18)` 偏移 (0,7) |
| 边框 | `rgba(218,221,226,205)`，1px |
| 背景 | `rgba(252,252,253,248)` |
| 标题字体 | Microsoft YaHei UI 11px DemiBold，`#25282D` |
| 副标题字体 | Microsoft YaHei UI 9px，`#747981` |
| 文本区域 | 左=38，右=130（为状态点留空间） |
| 状态点 | 圆心 x=窗口宽-53，y=49；外圆半径 23，内图标 3px 圆头线条 |
| 状态配色 | SUCCESS 绿 / ERROR 红 / WAITING 黄 / THINKING 蓝 / WORKING 蓝 / 其他灰 |

## 4. 实现文件

- `runtime/pet/speech_bubble.py`：已替换为 EAC 原生卡片复刻。
- `runtime/pet/window.py`：`show_bubble` 增加 `state` 参数。
- `runtime/eac_entry.py`：状态气泡传递 `state`，并组合标题+副标题。
- `docs/native-bubble-preview.png`：渲染预览（由 preview 文件复制）。

## 5. 验证

- 默认文字：`我在这儿等新任务哦` / `Codex · 等待下一次任务`。
- 收到 Hook 后，副标题前缀切换为当前任务模型，例如 `GPT-5.6 Sol · 正在执行任务`。
- `inspect_image` 确认：大圆角、双层阴影、主标题加粗深灰、副标题浅灰、右侧状态圆点均与 EAC 原生卡片一致。
