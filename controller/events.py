from __future__ import annotations

import hashlib
import re
import time
from typing import Any


PROTOCOL_VERSION = 2
ALLOWED_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "Stop",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


def safe_identifier(value: Any) -> str:
    text = str(value or "")
    if _SAFE_ID.fullmatch(text):
        return text
    if not text:
        return ""
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:20]


def safe_tool_name(value: Any) -> str:
    text = str(value or "unknown")
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]", "_", text)[:96]
    return cleaned or "unknown"


def safe_model_slug(value: Any) -> str:
    """Keep only bounded public model identifiers from the hook payload."""
    text = str(value or "").strip()
    return text if _SAFE_MODEL.fullmatch(text) else ""


def model_label(value: Any) -> str:
    """Turn Codex model slugs into compact user-facing bubble labels."""
    slug = safe_model_slug(value)
    if not slug or not slug.lower().startswith("gpt-"):
        return "Codex"
    parts = slug[4:].split("-")
    version = parts[0]
    suffix = " ".join(part.capitalize() for part in parts[1:] if part)
    return f"GPT-{version}" + (f" {suffix}" if suffix else "")


def state_detail(state: Any) -> str:
    return {
        "IDLE": "等待下一次任务",
        "THINKING": "正在思考",
        "WORKING": "正在执行任务",
        "WAITING": "等待你的确认",
        "SUCCESS": "任务已完成",
        "ERROR": "执行遇到问题",
        "DISCONNECTED": "等待 Codex",
    }.get(str(state or "IDLE").upper(), "等待下一次任务")


def _response_failed(response: Any) -> bool:
    """Read status flags only. Never copy the response into the outgoing event."""
    if not isinstance(response, dict):
        return False
    for key in ("isError", "is_error", "error", "failed"):
        value = response.get(key)
        if isinstance(value, bool) and value:
            return True
    for key in ("exit_code", "exitCode", "status_code"):
        value = response.get(key)
        if isinstance(value, int) and value != 0:
            return True
    return False


def _tool_presentation(tool_name: str) -> tuple[str, str]:
    lower = tool_name.lower()
    if lower in {"apply_patch", "edit", "write"}:
        return "edit", "正在修改文件"
    if lower == "bash":
        return "command", "正在运行命令"
    if lower == "update_plan":
        return "plan", "正在更新任务进度"
    if "browser" in lower or "web" in lower:
        return "browser", "正在查找资料"
    if "image" in lower:
        return "image", "正在处理图像"
    if lower.startswith("mcp__"):
        return "connector", "正在调用连接工具"
    return "tool", "正在使用工具"


def adapt_codex_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a Codex hook payload into a bounded, non-sensitive v2 event."""
    event_name = str(payload.get("hook_event_name") or "")
    if event_name not in ALLOWED_EVENTS:
        raise ValueError(f"unsupported hook event: {event_name!r}")

    result: dict[str, Any] = {
        "protocolVersion": PROTOCOL_VERSION,
        "kind": "event",
        "event": event_name,
        "sessionId": safe_identifier(payload.get("session_id")),
        "turnId": safe_identifier(payload.get("turn_id")),
        "timestamp": int(time.time() * 1000),
        "modelSlug": safe_model_slug(payload.get("model")),
        "modelLabel": model_label(payload.get("model")),
    }
    tool_name = safe_tool_name(payload.get("tool_name"))
    tool_category, tool_message = _tool_presentation(tool_name)

    if event_name == "SessionStart":
        result.update(state="IDLE", message="Codex 已连接")
    elif event_name == "UserPromptSubmit":
        result.update(state="THINKING", message="收到任务，开始处理")
    elif event_name == "PreToolUse":
        result.update(
            kind="tool-start",
            state="WORKING",
            message=tool_message,
            toolName=tool_name,
            toolCategory=tool_category,
            toolUseId=safe_identifier(payload.get("tool_use_id")),
        )
    elif event_name == "PostToolUse":
        failed = _response_failed(payload.get("tool_response"))
        message = "工具执行遇到问题" if failed else (
            "任务步骤已更新" if tool_category == "plan" else "工具执行完成，继续处理"
        )
        result.update(
            kind="tool-end",
            state="ERROR" if failed else "THINKING",
            message=message,
            toolName=tool_name,
            toolCategory=tool_category,
            toolUseId=safe_identifier(payload.get("tool_use_id")),
            failed=failed,
        )
    elif event_name == "PermissionRequest":
        result.update(
            kind="permission-request",
            state="WAITING",
            message="需要你确认这次操作",
            toolName=tool_name,
            toolCategory=tool_category,
        )
    elif event_name == "Stop":
        result.update(kind="turn-stop", state="SUCCESS", message="本轮工作已完成")
    return result


def runtime_message(event: dict[str, Any], visible: bool = True) -> dict[str, Any]:
    """Translate sanitized v2 events to the existing pet runtime protocol v1."""
    state = str(event.get("state") or "IDLE")
    message = str(event.get("message") or "")[:160]
    agent_label = model_label(event.get("modelSlug"))
    kind = "pulse" if event.get("kind") in {"tool-end", "turn-stop"} else "state"
    if event.get("event") == "UserPromptSubmit":
        kind = "task"
    return {
        "protocolVersion": 1,
        "kind": kind,
        "state": state,
        "message": message,
        "detail": f"{agent_label} · {state_detail(state)}",
        "agentLabel": agent_label,
        "visible": bool(visible),
    }
