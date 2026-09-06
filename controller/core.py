from __future__ import annotations

import time
import threading
from queue import Empty, Queue
from typing import Any

from .config import ConfigStore
from .events import ALLOWED_EVENTS, model_label, runtime_message, state_detail


class ControllerCore:
    MISSING_PROBES_BEFORE_EXIT = 2
    FAREWELL_FALLBACK_SECONDS = 25.0

    def __init__(self, config: ConfigStore, pet, process_probe, inbox: Queue | None = None) -> None:
        self.config = config
        self.pet = pet
        self.process_probe = process_probe
        self.inbox = inbox or Queue()
        self.codex_running = False
        self.current_state = "IDLE"
        self.current_message = "等待 Codex"
        self.current_agent_label = "Codex"
        self.bridge_active = False
        self.last_error = ""
        self.restart_not_before = 0.0
        self.active_tools: set[tuple[str, str, str]] = set()
        self.missing_process_probes = 0
        self.codex_exit_confirmed = False
        self.farewell_active = False
        self.farewell_deadline = 0.0
        self._message_lock = threading.RLock()

    def tick_process(self) -> None:
        # Process polling is the lifecycle heartbeat. Draining here provides a
        # second delivery path if a GUI refresh timer is delayed or recreated.
        self.drain()
        running = bool(self.process_probe())
        if running:
            self._mark_codex_running()
        elif self.codex_running:
            self.missing_process_probes += 1
            if self.missing_process_probes >= self.MISSING_PROBES_BEFORE_EXIT:
                self.codex_running = False
                self.bridge_active = False
                self.codex_exit_confirmed = True
                self.current_state = "DISCONNECTED"
                self.current_message = "Codex 已关闭，下次见"
                self.current_agent_label = "Codex"
                self.active_tools.clear()
                self._begin_farewell()
        self._tick_farewell_timeout()
        self._reconcile()

    def tick_pet(self) -> None:
        self.pet.poll()
        self._tick_farewell_timeout()
        self._reconcile()

    def drain(self) -> None:
        while True:
            try:
                message = self.inbox.get_nowait()
            except Empty:
                break
            self.handle_message(message)

    def handle_message(self, message: dict[str, Any]) -> None:
        # Bridge and pet stdout callbacks run on background threads. All state
        # transitions and pipe writes are serialized here; no Qt widget is
        # touched by ControllerCore.
        with self._message_lock:
            self._handle_message_locked(message)

    def _handle_message_locked(self, message: dict[str, Any]) -> None:
        if message.get("source") == "pet":
            self._handle_pet_message(message)
            return
        if message.get("kind") == "control":
            self._handle_control(message)
            return
        if message.get("protocolVersion") != 2 or message.get("event") not in ALLOWED_EVENTS:
            return
        if not self.config.get("enhanced_enabled"):
            return
        # Hooks are global lifecycle signals and can also be emitted by Codex
        # surfaces outside the desktop app.  A strict process probe is the only
        # authority allowed to start, revive, or update the desktop pet.
        if not bool(self.process_probe()):
            self._record_hook(message, applied=False)
            return
        self._mark_codex_running()
        self._record_hook(message, applied=True)
        self._reconcile()
        self.current_agent_label = model_label(message.get("modelSlug"))
        tool_key = (
            str(message.get("sessionId") or ""),
            str(message.get("turnId") or ""),
            str(message.get("toolUseId") or ""),
        )
        if message.get("kind") == "tool-start":
            self.active_tools.add(tool_key)
        elif message.get("kind") == "tool-end":
            self.active_tools.discard(tool_key)
            if self.active_tools and not message.get("failed"):
                message = dict(message)
                message.update(state="WORKING", message="仍在处理其他工具")
        elif message.get("kind") == "turn-stop":
            self.active_tools.clear()
        self.current_state = str(message.get("state") or "IDLE")
        self.current_message = str(message.get("message") or "")[:160]
        if self.pet.running:
            runtime = runtime_message(message, visible=self.config.get("visible", True))
            runtime["agentLabel"] = self.current_agent_label
            runtime["detail"] = f"{self.current_agent_label} · {state_detail(runtime.get('state'))}"
            self.pet.send(runtime)

    def _handle_pet_message(self, message: dict[str, Any]) -> None:
        kind = message.get("kind")
        if kind == "ready":
            self.pet.ready = True
            self.pet.send({
                "protocolVersion": 1,
                "kind": "hello",
                "state": self.current_state,
                "message": self.current_message,
                "detail": f"{self.current_agent_label} · {state_detail(self.current_state)}",
                "agentLabel": self.current_agent_label,
                "visible": bool(self.config.get("visible", True)),
            })
        elif kind == "visibility":
            visible = bool(message.get("visible"))
            self.config.set("visible", visible)
            self._send_visibility(visible)
        elif kind == "closed":
            self.disable_until_manual_reopen()
        elif kind == "farewell-complete":
            if self.farewell_active:
                self.farewell_active = False
                self.farewell_deadline = 0.0
                self.pet.stop("codex-exit")
        elif kind == "start-error":
            self.last_error = str(message.get("detail") or "start-error")
            self.restart_not_before = time.monotonic() + 5.0
        elif kind == "exit":
            expected = message.get("expected")
            code = int(message.get("code") or 0)
            if expected:
                return
            if self.codex_exit_confirmed:
                self.farewell_active = False
                self.farewell_deadline = 0.0
                return
            if code == 0:
                # A clean, unrequested exit is the runtime's "退出增强桌宠".
                self.disable_until_manual_reopen()
            else:
                self.last_error = f"pet-exit-{code}"
                self.restart_not_before = time.monotonic() + 1.5

    def _handle_control(self, message: dict[str, Any]) -> None:
        action = message.get("action")
        if action == "manual-open":
            self.codex_exit_confirmed = False
            self.config.update(enhanced_enabled=True, auto_accompany=True, visible=True)
            self._reconcile(force=True)
        elif action == "show":
            self.config.update(enhanced_enabled=True, visible=True)
            self._reconcile(force=True)
            self._send_visibility(True)
        elif action == "hide":
            self.config.set("visible", False)
            self._send_visibility(False)
        elif action == "set-auto-accompany":
            self.config.set("auto_accompany", bool(message.get("enabled")))
            self._reconcile()
        elif action == "disable":
            self.disable_until_manual_reopen()

    def _send_visibility(self, visible: bool) -> None:
        if self.pet.running:
            self.pet.send({
                "protocolVersion": 1,
                "kind": "state",
                "state": self.current_state,
                "message": self.current_message,
                "detail": f"{self.current_agent_label} · {state_detail(self.current_state)}",
                "agentLabel": self.current_agent_label,
                "visible": visible,
            })

    def disable_until_manual_reopen(self) -> None:
        self.farewell_active = False
        self.farewell_deadline = 0.0
        self.config.set("enhanced_enabled", False)
        self.active_tools.clear()
        self.pet.stop("user-disabled")

    def _reconcile(self, force: bool = False) -> None:
        should_run = (
            self.codex_running
            and bool(self.config.get("enhanced_enabled"))
            and (bool(self.config.get("auto_accompany")) or force)
        )
        if should_run and not self.pet.running and time.monotonic() >= self.restart_not_before:
            self.pet.start(visible=bool(self.config.get("visible", True)))
        elif not self.codex_running and self.pet.running and not self.farewell_active:
            self.pet.stop("codex-exit")

    def _mark_codex_running(self) -> None:
        self.missing_process_probes = 0
        self.codex_exit_confirmed = False
        if self.farewell_active:
            self._cancel_farewell()
        if not self.codex_running:
            self.codex_running = True
            self.bridge_active = True
            self.current_state = "IDLE"
            self.current_message = "检测到 Codex"
            self.current_agent_label = "Codex"

    def _record_hook(self, message: dict[str, Any], *, applied: bool) -> None:
        label = model_label(message.get("modelSlug"))
        ignored_count = int(self.config.get("hook_ignored_count", 0))
        self.config.update(
            hook_event_count=int(self.config.get("hook_event_count", 0)) + 1,
            hook_last_event=str(message.get("event") or "")[:64],
            hook_last_received_at=int(time.time()),
            hook_last_model_slug=str(message.get("modelSlug") or "")[:96],
            hook_last_model_label=label,
            hook_last_applied=applied,
            hook_ignored_count=ignored_count + (0 if applied else 1),
        )

    def _begin_farewell(self) -> None:
        if not self.pet.running:
            return
        if not bool(self.config.get("visible", True)):
            self.pet.stop("codex-exit")
            return
        self.farewell_active = True
        self.farewell_deadline = time.monotonic() + self.FAREWELL_FALLBACK_SECONDS
        self.pet.send({
            "protocolVersion": 1,
            "kind": "farewell",
            "state": "DISCONNECTED",
            "message": "Codex 已关闭，下次见",
            "detail": "Codex · 本次陪伴结束",
            "agentLabel": "Codex",
            "animation": "点击回应 - 元气挥手",
            "bubbleDurationMs": 6000,
            "playbackSpeed": 1.0,
            "visible": True,
        })

    def _cancel_farewell(self) -> None:
        if not self.farewell_active:
            return
        self.farewell_active = False
        self.farewell_deadline = 0.0
        if self.pet.running:
            self.pet.send({"protocolVersion": 1, "kind": "farewell-cancel"})
        self.current_state = "IDLE"
        self.current_message = "检测到 Codex"
        self.current_agent_label = "Codex"
        self._send_visibility(bool(self.config.get("visible", True)))

    def _tick_farewell_timeout(self) -> None:
        if self.farewell_active and time.monotonic() >= self.farewell_deadline:
            self.farewell_active = False
            self.farewell_deadline = 0.0
            self.last_error = "farewell-timeout"
            self.pet.stop("codex-exit-timeout")

    def status_text(self) -> str:
        received_at = int(self.config.get("hook_last_received_at", 0) or 0)
        if received_at:
            age = max(0, int(time.time()) - received_at)
            if self.config.get("hook_last_applied"):
                hook_status = (
                    f"Hook：已接收并用于 Codex 桌宠，最近 {self.config.get('hook_last_event') or '事件'}，"
                    f"{age} 秒前，共 {self.config.get('hook_event_count', 0)} 次"
                )
            else:
                hook_status = (
                    "Hook：已收到但忽略，未检测到 Codex 桌面客户端，"
                    f"最近 {self.config.get('hook_last_event') or '事件'}，{age} 秒前，"
                    f"已忽略 {self.config.get('hook_ignored_count', 0)} 次"
                )
        else:
            audit = self.config.hook_audit()
            if audit and audit.get("sendOk") is False:
                hook_status = "Hook：已触发，但本机任务桥接不可用"
            else:
                hook_status = "Hook：从未收到，请在 Codex CLI 输入 /hooks 审核并信任"
        return "\n".join([
            f"Codex：{'运行中' if self.codex_running else '未运行'}",
            f"增强桌宠：{'告别中' if self.farewell_active else ('运行中' if self.pet.running else '未运行')}",
            f"任务桥接：{'已连接' if self.bridge_active else '已暂停'}",
            hook_status,
            f"当前模型：{self.current_agent_label}",
            f"自动伴随：{'开启' if self.config.get('auto_accompany') else '关闭'}",
            f"下次允许启动：{'是' if self.config.get('enhanced_enabled') else '否，需手动打开'}",
            f"状态：{self.current_message or self.current_state}",
            *( [f"最近错误：{self.last_error}"] if self.last_error else [] ),
        ])
