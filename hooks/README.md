# Codex Hooks 模板

`hooks.json.template` 配置六个只读通知 Hook：`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`PermissionRequest`、`Stop`。所有命令均为 `async: true`，失败时静默退出，不阻断或改变 Codex 的任务、工具和审批流程。

安装时把模板复制或合并到用户级 `~/.codex/hooks.json`，并将 `commandWindows` 中 `invoke_hook.ps1` 和 `-DataDir` 替换为实际绝对路径。不要覆盖用户已有 Hook。数据目录固定为 `~/.codex/dafeiyu-companion-data`，不会受 Codex AppContainer 的 AppData 虚拟化影响。PowerShell 启动器会读取控制器记录的实际 Python 路径，因此不依赖系统安装 `py` 或 `python` 命令。Codex 会要求用户审核并信任新增或变更的 Hook 定义。

脚本只发送：事件类型、匿名安全 ID、经过字符限制的公开模型标识、工具名、工具类别、是否失败以及预定义中文状态文案。它不会发送用户提示、工作目录、会话转录路径、工具参数、完整命令或工具输出。

每次调用会覆盖写入一份 `hook-audit.json`，只包含事件、模型、工具类别、时间和本机桥接是否成功，用于托盘诊断。它不是对话日志，不保存任务正文。
