# dsh-pet-indesktop（EAC 独立桌宠集成）

将 `MerZlin/dsh-pet-indesktop` 的桌面宠物核心（透明 WebM 动画、点击/拖拽/移动交互）接入 EAC，作为独立插件运行；不修改、不覆盖 EAC 自带的大肥鱼（`dsh-dafeiyu`）和网页桌宠（`dsh-pet`）。

## 功能

- 桌面置顶透明窗口，播放 640×360 透明 WebM 动画（待机 / 转向 / 移动 / 点击回应 / 拖拽 / 随机动作）。
- 监听 DSH `session/event`，把 EAC 工作状态映射为动画：
  - `THINKING`：分析/思考类动作
  - `WORKING`：工具执行类动作
  - `WAITING`：等待确认/小憩
  - `SUCCESS`：开心回应
  - `ERROR`：受惊/气急败坏
  - `IDLE`：随机动画链（与上游一致）
- 设置页新增「独立桌宠」分区，可创建、显示、隐藏、移除卡片；每张卡片对应一个独立桌面宠物窗口。
- 冗余功能默认关闭：不启动 AI 聊天、余额查询、更新检查、开机自启；右键菜单只保留动画/大小/置顶/隐藏等桌宠自身交互。

## 目录

```
dsh-pet-indesktop/
├─ package.json
├─ cordis.patch.yml
├─ src/                 # DSH 宿主半（会话事件 -> 状态 -> helper 进程）
├─ lib/client.js        # EAC 设置页卡片 UI
├─ runtime/
│  ├─ eac_entry.py      # EAC 桥接入口（stdio JSON 协议）
│  ├─ pet/              # 上游桌面宠物核心（仅保留展示所需模块）
│  └─ assets/           # 分类 WebM 动画与音效
├─ README.md / INSTALL.md / LICENSE
└─ requirements.txt
```

## 安装

1. 将插件目录复制到当前 profile 的 `node_modules`：
   `%USERPROFILE%\.dsh\profiles\web-desktop\node_modules\dsh-pet-indesktop`
2. 在 `cordis.patch.yml` 登记：
   ```yaml
   - insert:
       - id: pet-indesktop
         name: dsh-pet-indesktop
   ```
   也可使用项目自带安装脚本：`node scripts/install-local.mjs`（如已提供）。
3. Python 依赖：
   ```powershell
   py -3 -m pip install -r requirements.txt
   ```
   需要 `PySide6`、`imageio-ffmpeg`（当前电脑已完成安装）。
4. 重启 dsh，刷新页面；在「设置 → 独立桌宠」中开关卡片。

## 回滚

- 删除 patch 中的 `pet-indesktop` 插入项（或设为 `disabled: true`），删除
  `node_modules\dsh-pet-indesktop` 目录，重启 dsh。
- 插件使用的配置目录为 `%APPDATA%\dsh-pet-eac`，与上游独立版互不影响；可删除该目录清理状态。

## 安全说明

- helper 只监听 stdin/stdout，由 DSH 宿主进程启动，不开放任何网络端口。
- 配置 HTTP 端点仅接受 127.0.0.1 且校验 Origin，与 dsh-dafeiyu 相同。
