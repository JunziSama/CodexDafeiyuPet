# -*- coding: utf-8 -*-
"""EAC bridge entry for dsh-pet-indesktop.

Runs the desktop pet core from the upstream repository, but removes the
standalone app services (AI chat, updater, balance, autostart). Instead it
speaks a line-delimited JSON protocol over stdin/stdout with the Codex
controller and switches animations from Codex work state.

Protocol (one JSON object per line, protocolVersion=1):
  -> {"kind":"hello","state":"IDLE","message":"..."}
  -> {"kind":"state","state":"THINKING","message":"...","detail":"..."}
  -> {"kind":"task","message":"...","task":"..."}
  -> {"kind":"pulse","state":"ERROR","message":"..."}
  -> {"kind":"shutdown"}
  <- {"protocolVersion":1,"kind":"ready"}
  <- {"protocolVersion":1,"kind":"pong"}
"""

from __future__ import annotations

import json
import os
import queue
import random
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The host writes UTF-8 JSON lines. On Chinese Windows, Python may default
# stdio to cp936, which corrupts Chinese bubble text; pin stdio to UTF-8.
for stream_name in ("stdin", "stdout", "stderr"):
    stream = getattr(sys, stream_name, None)
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Use an EAC-specific data directory so this integration never shares or
# overwrites the standalone desktop app configuration.
os.environ.setdefault("DSH_PET_APP_DIR_NAME", "dsh-pet-eac")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.library import MovieLibrary
from pet.window import PetWindow

ASSET_DIR = ROOT / "assets" / "characters" / "shenshen" / "videos"

STATE_PRIORITY = {
    "ERROR": 100,
    "WAITING": 90,
    "WORKING": 80,
    "THINKING": 70,
    "SUCCESS": 60,
    "IDLE": 10,
    "DISCONNECTED": 0,
}

SCENE_DEFAULT = {
    "IDLE": ["待机呼吸休闲"],
    "THINKING": ["深度思考碎碎念", "原地专心玩魔方", "写代码"],
    "WORKING": ["原地敲击桌面互动", "写代码", "玩游戏气急败坏"],
    "WAITING": ["原地小憩沉眠", "打瞌睡被惊醒"],
    "SUCCESS": ["点击回应 - 开心跃动"],
    "ERROR": ["被吓一跳", "玩游戏气急败坏"],
    "DISCONNECTED": ["原地小憩沉眠"],
}

SCENE_ALTERNATE = {
    "THINKING": ["下五子棋", "轻快记录", "吃Token", "照镜子"],
    "WORKING": ["原地跳跃抓碎头顶物品", "玩水枪", "变鸽子", "凭空生花"],
    "WAITING": ["哈欠连天", "超大伸懒腰", "女仆屈膝礼仪", "悠闲哼歌"],
    "SUCCESS": ["点击回应 - 元气挥手", "点击回应 - 害羞惊讶", "点击回应 - 傲娇生气"],
    "ERROR": ["被吓一跳", "用鲸鱼尾巴拍打地面"],
}

TASK_ANIMATIONS = [
    "原地敲击桌面互动",
    "写代码",
    "吃Token",
    "轻快记录",
    "原地专心玩魔方",
    "下五子棋",
    "玩游戏气急败坏",
]

# Every animation not explicitly listed above still participates in the
# least-recently-used idle/task pools, so coverage converges to 100%.
IDLE_ANIMATIONS = [
    "待机呼吸休闲",
    "东张西望",
    "原地小憩沉眠",
    "哈欠连天",
    "超大伸懒腰",
    "悠闲哼歌",
    "小提琴演奏",
    "优雅女仆舞",
    "可爱宅舞",
    "轻快摇摆舞",
    "轻快记录",
    "撸猫",
]


class AnimationScheduler:
    """Least-recently-used pool scheduler with repeat protection."""

    def __init__(self, names) -> None:
        self.names = list(names)
        self.name_by_key = {self._key(name): name for name in self.names}
        self.use_count = {name: 0 for name in self.names}
        self.last_used_at = {name: -1.0 for name in self.names}
        self.recent: list[str] = []

    @staticmethod
    def _key(name) -> str:
        return "".join(str(name or "").split())

    def available(self, pool) -> list[str]:
        result: list[str] = []
        for requested in pool:
            name = requested if requested in self.use_count else self.name_by_key.get(self._key(requested))
            if name is not None and name not in result:
                result.append(name)
        return result

    def choose(self, pool, now=0.0, exclude=None) -> str | None:
        candidates = self.available(pool)
        if not candidates:
            return None
        if exclude is not None:
            narrowed = [name for name in candidates if name != exclude]
            if narrowed:
                candidates = narrowed
        if len(candidates) > 1:
            recent = set(self.recent[-2:])
            outside_recent = [name for name in candidates if name not in recent]
            if outside_recent:
                candidates = outside_recent
        return min(
            candidates,
            key=lambda name: (self.last_used_at.get(name, -1.0), self.use_count.get(name, 0), random.random()),
        )

    def record(self, name, now=0.0) -> None:
        if name not in self.use_count:
            self.use_count[name] = 0
        self.use_count[name] += 1
        self.last_used_at[name] = now
        self.recent.append(name)
        if len(self.recent) > 12:
            self.recent.pop(0)



class EacPetController:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.queue: queue.Queue = queue.Queue()
        self.window: PetWindow | None = None
        self.visible = os.environ.get("DSH_PET_VISIBLE", "1") == "1"
        self.card_id = os.environ.get("DSH_PET_CARD_ID", "card-0")
        self.config = Config()
        self.config.set("self_talk_enabled", False)
        self.config.set("click_show_balance", False)
        self.config.set("click_show_self_talk", False)
        self.config.set("autostart_wanted", False)
        self.config.set("chat", self.config.data.get("chat", {}))
        self.config.save()

        self.library = MovieLibrary(asset_dir=ASSET_DIR)
        self.window = PetWindow(self.library, self.config)
        self.window.on_open_chat = None
        self.window.on_open_chat_settings = None
        self.window.on_open_settings = None
        self.window.on_check_update = None
        self.window.on_show_balance = None
        self.window.on_look_synced = None
        self.window.animation_finished.connect(self._on_animation_finished)
        self.window.animation_started.connect(self._on_animation_started)
        self.window.bubble_dismissed.connect(self._on_bubble_dismissed)
        self.window.visibility_requested.connect(self._request_visibility)
        self.window.setWindowTitle("Codex Dafeiyu " + self.card_id)

        # Offset multiple cards so they do not overlap exactly.
        try:
            offset = int(os.environ.get("DSH_PET_CARD_OFFSET", "0"))
        except ValueError:
            offset = 0
        if offset:
            self.window.move(max(0, self.window.x() - offset), max(0, self.window.y() - offset))

        self.names = list(self.library.names())
        self.scheduler = AnimationScheduler(self.names)
        self.current_state = "DISCONNECTED"
        self.current_animation = self.window.anim
        self.current_origin = "idle"
        self.playing_state = "DISCONNECTED"
        self.last_pick_at = 0.0
        self.pick_phase = "default"
        self.last_message = ""
        self.agent_label = "Codex"
        self.farewell_requested = False
        self.farewell_phase = ""
        self.farewell_animation = ""
        self.farewell_mode = "farewell_only"
        self.farewell_current_finished = False
        self.farewell_window_hidden = False
        self._pre_farewell_speed: float | None = None
        self._farewell_wait_timer = QTimer()
        self._farewell_wait_timer.setSingleShot(True)
        self._farewell_wait_timer.timeout.connect(self._on_farewell_wait_timeout)
        self._farewell_animation_timer = QTimer()
        self._farewell_animation_timer.setSingleShot(True)
        self._farewell_animation_timer.timeout.connect(self._complete_farewell)

        self._poll = QTimer()
        self._poll.setInterval(80)
        self._poll.timeout.connect(self._drain)
        self._poll.start()

    def show_ready(self) -> None:
        print(json.dumps({"protocolVersion": 1, "kind": "ready"}), flush=True)

    def apply_visible(self, visible: bool | None) -> None:
        if visible is not None:
            self.visible = bool(visible)
        if self.window is None:
            return
        if self.visible:
            self.window.show()
            self.window.raise_()
        else:
            self.window.hide()

    def _request_visibility(self, visible: bool) -> None:
        self.visible = bool(visible)
        self.apply_visible(self.visible)
        print(json.dumps({
            "protocolVersion": 1,
            "kind": "visibility",
            "visible": self.visible,
        }), flush=True)

    def _can_interrupt(self) -> bool:
        if self.window is None:
            return True
        # Never yank a drag animation out from under the mouse.
        return not bool(getattr(self.window, "_dragging", False))

    def _pool_for_state(self, state: str) -> list[str]:
        base = SCENE_DEFAULT.get(state, [])
        alternate = SCENE_ALTERNATE.get(state, [])
        pool = base + alternate
        if state == "IDLE":
            pool = IDLE_ANIMATIONS + list(SCENE_DEFAULT.get(state, [])) + ["东张西望"]
        return self.scheduler.available(pool)

    def _play(
        self,
        name: str | None,
        now: float,
        state: str | None = None,
        origin: str = "controller",
    ) -> bool:
        if self.window is None or name is None or name not in self.names:
            return False
        self.current_animation = name
        self.current_origin = str(origin or "controller")
        self.playing_state = str(state or self.current_state)
        self.window._switch(name, origin=self.current_origin)
        self.scheduler.record(name, now)
        self.last_pick_at = now
        return True

    def _on_animation_started(self, name: str, origin: str) -> None:
        """Synchronize controller state with direct click/menu/window switches."""
        self.current_animation = str(name)
        self.current_origin = str(origin or "idle")

    def _choose_for_state(self, state: str, now: float) -> str | None:
        if state == "IDLE":
            idle_pool = list(getattr(self.window, "idles", [])) if self.window is not None else []
            return self.scheduler.choose(idle_pool or ["待机呼吸休闲"], now)

        if self.pick_phase == "alternate":
            alternate = self.scheduler.available(SCENE_ALTERNATE.get(state, []))
            if alternate:
                return self.scheduler.choose(alternate, now, exclude=self.current_animation)

        pool = self._pool_for_state(state)
        if pool:
            return self.scheduler.choose(pool, now, exclude=self.current_animation)

        # Fallback: least-recently-used random action keeps coverage complete.
        return self.scheduler.choose(self.names, now, exclude=self.current_animation)

    def _play_idle_next(self, now: float) -> None:
        if self.window is None:
            return
        probability = self.window.movement_probability()
        if probability > 0 and random.random() < probability:
            if self.window._try_move_with_turnaround(origin="movement"):
                name = self.window.anim
                self.scheduler.record(name, now)
                self.current_animation = name
                self.current_origin = "movement"
                self.playing_state = "IDLE"
                self.last_pick_at = now
                return
        if self.window.idle_action_due(now):
            pool = list(self.window.turns) + list(self.window.acts)
            choice = self.scheduler.choose(pool, now, exclude=self.current_animation)
            if choice is not None:
                self.window.mark_idle_action(now)
                self._play(choice, now, state="IDLE", origin="idle")
                return
        self._play(self._choose_for_state("IDLE", now), now, state="IDLE", origin="idle")

    def _on_animation_finished(self, name: str) -> None:
        """Apply the newest Codex state only after the current clip completes."""
        if self.window is None or name != self.current_animation:
            return
        if self.farewell_requested:
            if self.farewell_mode == "bubble_sync":
                self.farewell_current_finished = True
                if hasattr(self.window, "hold_finished_animation"):
                    self.window.hold_finished_animation()
            elif self.farewell_mode == "current_only":
                self._complete_farewell()
            elif self.farewell_phase == "playing" and self.current_origin == "farewell":
                self._complete_farewell()
            elif self.farewell_mode == "current_then_farewell":
                self._start_farewell_animation()
            return
        now = time.monotonic()
        if self.current_state in {"SUCCESS", "ERROR"} and self.playing_state == self.current_state:
            self.current_state = "IDLE"
            self.pick_phase = "default"
            self._play_idle_next(now)
            return
        if self.current_state == "IDLE":
            self._play_idle_next(now)
            return
        self.pick_phase = "alternate" if self.pick_phase == "default" else "default"
        self._play(self._choose_for_state(self.current_state, now), now, origin="controller")

    def _bubble_text(self, message: str, detail: str) -> str:
        if message and detail and detail not in message:
            return f"{message}\n{detail}"
        return message or detail

    def begin_farewell(self, payload: dict) -> None:
        if self.window is None or self.farewell_requested:
            return
        self.farewell_requested = True
        self.farewell_animation = str(payload.get("animation") or "点击回应 - 元气挥手")
        self.farewell_mode = str(getattr(self.window, "exit_animation_mode", "farewell_only"))
        if self.farewell_mode not in {
            "current_then_farewell", "farewell_only", "current_only", "bubble_sync",
        }:
            self.farewell_mode = "farewell_only"
        self.farewell_current_finished = False
        self.farewell_window_hidden = False
        self.current_state = "DISCONNECTED"
        self.agent_label = str(payload.get("agentLabel") or "Codex")[:96]
        message = str(payload.get("message") or "Codex 已关闭，下次见").strip()
        detail = str(payload.get("detail") or "Codex · 本次陪伴结束").strip()
        bubble = self._bubble_text(message, detail)
        duration = max(1000, min(12000, int(payload.get("bubbleDurationMs") or 6000)))
        if bubble and self.visible:
            self.window.show_bubble(bubble, duration_ms=duration, state="DISCONNECTED")
            self.last_message = bubble
        self.window.set_interactions_locked(True)
        if self.farewell_mode == "farewell_only":
            self._start_farewell_animation()
        elif self.farewell_mode == "bubble_sync":
            self.farewell_phase = "waiting_bubble"
            # The bubble signal is authoritative; this timer only handles a
            # hidden/destroyed bubble that cannot report its normal dismissal.
            self._farewell_wait_timer.start(duration + 250)
        elif self.current_animation:
            self.farewell_phase = "waiting"
            self._farewell_wait_timer.start(12000)
        elif self.farewell_mode == "current_then_farewell":
            self._start_farewell_animation()
        else:
            self._complete_farewell()

    def _start_farewell_animation(self) -> None:
        if self.window is None or not self.farewell_requested or self.farewell_phase == "playing":
            return
        self._farewell_wait_timer.stop()
        self.farewell_phase = "playing"
        if self._pre_farewell_speed is None:
            self._pre_farewell_speed = float(self.window.playback_speed)
        self.window.playback_speed = 1.0
        available = self.scheduler.available([self.farewell_animation])
        name = available[0] if available else None
        if not self._play(name, time.monotonic(), state="DISCONNECTED", origin="farewell"):
            self._complete_farewell()
            return
        self._farewell_animation_timer.start(12000)

    def _on_farewell_wait_timeout(self) -> None:
        """Advance only when the current clip or bubble cannot finish normally."""
        if self.farewell_mode == "current_then_farewell":
            self._start_farewell_animation()
        else:
            self._complete_farewell()

    def _on_bubble_dismissed(self) -> None:
        if (
            self.farewell_requested
            and self.farewell_mode == "bubble_sync"
            and self.farewell_phase == "waiting_bubble"
        ):
            self._complete_farewell(hide_window=True)

    def _complete_farewell(self, hide_window: bool = False) -> None:
        if not self.farewell_requested or self.farewell_phase == "complete":
            return
        self._farewell_wait_timer.stop()
        self._farewell_animation_timer.stop()
        self.farewell_phase = "complete"
        if hide_window and self.window is not None:
            if hasattr(self.window, "interrupt_current_animation"):
                self.window.interrupt_current_animation()
            self.window.hide()
            self.farewell_window_hidden = True
        if self.window is not None and hasattr(self.window, "hold_finished_animation"):
            self.window.hold_finished_animation()
        print(json.dumps({"protocolVersion": 1, "kind": "farewell-complete"}), flush=True)

    def cancel_farewell(self) -> None:
        if self.window is None or not self.farewell_requested:
            return
        was_playing = (
            self.farewell_phase in {"playing", "complete"}
            or (self.farewell_mode == "bubble_sync" and self.farewell_current_finished)
        )
        self._farewell_wait_timer.stop()
        self._farewell_animation_timer.stop()
        self.farewell_requested = False
        self.farewell_phase = ""
        self.window.set_interactions_locked(False)
        if self._pre_farewell_speed is not None:
            self.window.playback_speed = self._pre_farewell_speed
            if self.window.movie is not None and hasattr(self.window.movie, "set_playback_speed"):
                self.window.movie.set_playback_speed(self._pre_farewell_speed)
        self._pre_farewell_speed = None
        if self.farewell_window_hidden and self.visible:
            self.window.show()
            self.window.raise_()
        self.farewell_window_hidden = False
        self.farewell_current_finished = False
        if was_playing:
            self.current_state = "IDLE"
            self.pick_phase = "default"
            self._play(self._choose_for_state("IDLE", time.monotonic()), time.monotonic(), state="IDLE", origin="idle")

    def apply_state(self, payload: dict) -> None:
        if self.window is None:
            return
        visible = payload.get("visible")
        if visible is not None:
            self.visible = bool(visible)
        self.apply_visible(self.visible)

        state = str(payload.get("state", "IDLE")).upper()
        if state not in STATE_PRIORITY:
            state = "IDLE"
        message = str(payload.get("message") or "").strip()
        self.agent_label = str(payload.get("agentLabel") or self.agent_label or "Codex")[:96]
        detail = str(payload.get("detail") or f"{self.agent_label} · 等待下一次任务").strip()
        bubble = self._bubble_text(message, detail)
        if bubble and self.visible and bubble != self.last_message:
            self.window.show_bubble(bubble, duration_ms=4200, state=state)
            self.last_message = bubble

        now = time.monotonic()
        state_changed = state != self.current_state
        self.current_state = state
        if state_changed:
            self.pick_phase = "default"
        # The active window animation is authoritative, including direct click
        # and menu selections. Hook updates only replace the single latest
        # desired state; animation_finished applies it at the clip boundary.
        if self.current_animation is None and self._can_interrupt():
            self._play(self._choose_for_state(state, now), now, origin="controller")

    def apply_task(self, payload: dict) -> None:
        self.apply_state(payload)

    def _drain(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                self._handle(message)
        except queue.Empty:
            pass

    def _handle(self, message: dict) -> None:
        kind = message.get("kind")
        if kind == "hello":
            self.show_ready()
            self.apply_visible(message.get("visible", self.visible))
            self.apply_state(message)
        elif kind == "state":
            self.apply_state(message)
        elif kind == "task":
            self.apply_task(message)
        elif kind == "pulse":
            self.apply_state(message)
        elif kind == "farewell":
            self.begin_farewell(message)
        elif kind == "farewell-cancel":
            self.cancel_farewell()
        elif kind == "shutdown":
            self.app.quit()
        elif kind == "ping":
            print(json.dumps({"protocolVersion": 1, "kind": "pong"}), flush=True)

    def run_reader(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("protocolVersion") != 1:
                continue
            self.queue.put(message)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    controller = EacPetController(app)
    threading.Thread(target=controller.run_reader, daemon=True).start()
    # The host queues HELLO/STATE until it receives READY, so READY must be
    # emitted proactively once the Qt event loop is about to start.
    QTimer.singleShot(0, controller.show_ready)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
