# 大肥鱼 Codex 托盘控制器

Windows 托盘控制器负责观察 Codex 桌面客户端进程，并在 Codex 运行且已启用时启动增强桌宠。Codex 完全退出后，桌宠与事件转发停止，托盘控制器继续驻留。

手动打开（开始菜单快捷方式应指向此命令）：

```powershell
& 'C:\path\to\python.exe' 'C:\path\to\CodexDafeiyuPet\controller\main.py' --enable
```

安装器应把自身使用的 Python 绝对路径写入开始菜单和登录启动快捷方式。不带 `--enable` 启动用于 Windows 登录后的托盘驻留，不会覆盖用户的“退出增强桌宠”选择。配置与桥接令牌保存在 `%USERPROFILE%\.codex\dafeiyu-companion-data`，避免 Codex AppContainer 对 AppData 的路径虚拟化。

托盘菜单提供显示、隐藏、随 Codex 自动启动、设置与状态以及彻底退出。桌宠窗口自身正常退出且返回码为 0 时，也按“退出增强桌宠”处理：关闭 `enhanced_enabled`，直到用户再次运行上述手动打开命令或点击托盘“显示大肥鱼”。

控制器只接受 `127.0.0.1` 上携带随机本机令牌的消息。它不会接收或记录用户提示、完整命令、工具参数或工具输出。

自动化冒烟测试可传入隐藏参数 `--smoke-seconds 2`，控制器会通过 Qt 主线程走完整关闭流程；不要用任务管理器或重复 `Ctrl+C` 强制结束 PySide6 托盘进程。
