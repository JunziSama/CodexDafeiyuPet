# 大肥鱼 Codex 增强桌宠开发说明

## 进程与数据流

Codex 生命周期 Hook 把去敏后的 v2 事件发送到 `127.0.0.1:46837`。托盘控制器校验本机桥接令牌，并以严格匹配的 Codex Windows 桌面进程作为桌宠生命周期的唯一依据；Hook 到达时会再次探测进程，未发现桌面客户端的事件只写入安全审计，不启动桌宠或改变任务状态。确认进程后，控制器通过标准输入向 `runtime/eac_entry.py` 发送 v1 运行时消息。桌宠通过标准输出报告 ready、visibility、closed、farewell-complete 等事件。

窗口的每次动画切换都携带 `controller`、`idle`、`movement`、`click`、`menu`、`drag` 或 `farewell` 来源。Hook 立即更新气泡，但动画状态只保留最新一份并在当前片段完成后接续。Codex 退出时，控制器连续两次确认进程消失后发送 `farewell`；运行时按配置 v5 的 `exit_animation_mode` 执行四种退场路径并回传 `farewell-complete`。重新启动 Codex 会发送 `farewell-cancel`。

运行时 v1 的可选 `animationCue` 只接受六个固定值：`task-thinking`、`tool-working`、`tool-finished`、`approval-waiting`、`task-success`、`task-error`。控制器依据去敏 Hook 事件生成 cue；窗口在当前片段边界应用最新 cue。对应的 6 个工作动画位于 `videos/events/work`。`videos/events/balance` 的 6 个余额动画没有可靠 Codex Hook，只出现在右键手选菜单。普通随机池共 83 个动画。

退出模式为 `current_then_farewell`、`farewell_only`、`current_only` 和 `bubble_sync`。模式由桌宠本地配置决定，运行时协议仍为 v1；退出开始后会锁定用户动画入口，本次退场使用开始时的配置快照。

运行代码安装在 `%USERPROFILE%\.codex\dafeiyu-companion`，用户数据在 `%USERPROFILE%\.codex\dafeiyu-companion-data`。`bridge-token`、日志和 Hook 审计均为机器运行数据，不得进入交付包。

## 开发入口

- 控制器：`controller/main.py`
- Hook 适配：`hooks/codex_event_hook.py` 与 `controller/events.py`
- 桌宠协议入口：`runtime/eac_entry.py`
- 窗口、菜单和物理：`runtime/pet/window.py`
- 播放库与解码：`runtime/pet/library.py`、`runtime/pet/webm_clip.py`
- 素材清单：`runtime/assets/characters/shenshen/asset-inventory.json`
- 安全偏好：`config/safe-preferences.json`

`MovieLibrary` 按需创建播放器，首帧缓存总预算为 8 MiB。任务 cue 会立即预测预热，低优先级预热在用户交互或窗口隐藏时暂停。WebM 使用 `-threads 1` 常驻循环 reader，在片段边界软停，并每 10 分钟只于边界回收；退出统一调用 `MovieLibrary.cleanup()`。高刷计时位于 `runtime/pet/timing.py`：90 Hz 以上按刷新率设定精确定时器，物理采用真实 elapsed time、50 ms 上限和 120 Hz 子步。

桌宠子进程启动失败按 1.5、3、6、12、30 秒退避；连续 5 次后锁定，稳定运行 60 秒清零。托盘“显示大肥鱼”可解除本次锁定。运行时错误只回传异常类别。

离线交付包带有 `portable-python`。源码目录开发时可向安装器传入 `-PythonRoot`，或让安装器检测本机 Codex bundled runtime。

## 验证命令

```powershell
python -m unittest discover -s controller\tests
$env:PYTHONPATH='runtime;runtime\vendor'; python -m unittest discover -s test
npm run check
npm test
```

Qt 离屏烟雾测试需设置 `QT_QPA_PLATFORM=offscreen`。Hook 定义变化后必须在 Codex CLI 中运行 `/hooks` 重新审核，禁止添加绕过信任的参数。

离线告别协议可单独验证：

```powershell
python scripts\smoke-farewell.py --package-root . --vendor-root runtime\vendor
python scripts\stress-runtime.py --package-root . --vendor-root runtime\vendor --iterations 100
```

长时稳定性验收在同一工具上增加 `--soak-seconds 1800`。素材变化后运行
`python scripts\generate-asset-inventory.py`，并提交生成的逐文件 SHA-256 清单。

独立公开版本使用 `scripts\build-release.ps1` 构建。源码仓库不提交 `runtime/vendor`；构建时通过
`-VendorSourceRoot` 指向已准备好的离线依赖目录。发布包必须携带 `ASSET_LICENSE.md`，且不得包含
Codex 原生 8×11 图集或其生成工程。

私有双桌宠仓库是开发源。公开仓库使用私库根目录的 `scripts\sync-public.ps1` 白名单同步；
必须先在独立公开克隆中创建 `codex/*` 任务分支。脚本会映射公开 README、保留未知根文件，
并拒绝错误 remote、公开 `main`、脏工作区、原生宠物、运行数据和用户专属路径。

## 常见故障

- Hook 为 Installed 但 Active 为 0：运行 `/hooks` 并信任六组定义。
- Hook 已发送但气泡不变：检查托盘状态、`hook-audit.json` 和本机 46837 端口；“已收到但忽略”表示事件到达时未检测到 Codex 桌面客户端，这是浏览器或其他 Codex 界面的预期隔离行为。
- 换机后 Python 不存在：使用离线交付包重新安装，或显式传入 `-PythonRoot`。
- 桌宠隐藏后不出现：从托盘选择“显示大肥鱼”；隐藏状态会持久化。
