from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.config import ConfigStore
from controller.core import ControllerCore
from controller.events import ALLOWED_EVENTS


class FakePet:
    def __init__(self):
        self.running = False
        self.ready = False
        self.started = []
        self.stopped = []
        self.sent = []

    def start(self, visible=True):
        self.running = True
        self.started.append(visible)
        return True

    def stop(self, reason):
        if self.running:
            self.stopped.append(reason)
        self.running = False

    def send(self, message):
        self.sent.append(message)
        return True

    def poll(self):
        return None


class CoreLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = ConfigStore(Path(self.temp.name))
        self.config.update(enhanced_enabled=True, auto_accompany=True, visible=True)
        self.pet = FakePet()
        self.running = False
        self.core = ControllerCore(self.config, self.pet, lambda: self.running)

    def tearDown(self):
        self.temp.cleanup()

    def test_codex_start_and_exit_manage_pet_but_not_controller(self):
        self.running = True
        self.core.tick_process()
        self.assertTrue(self.pet.running)
        self.running = False
        self.core.tick_process()
        self.assertTrue(self.pet.running)
        self.core.tick_process()
        self.assertTrue(self.core.farewell_active)
        self.assertEqual(self.pet.sent[-1]["kind"], "farewell")
        self.core.handle_message({"source": "pet", "kind": "farewell-complete"})
        self.assertFalse(self.pet.running)
        self.assertEqual(self.pet.stopped, ["codex-exit"])

    def test_clean_unrequested_pet_exit_disables_until_manual_open(self):
        self.running = True
        self.core.tick_process()
        self.pet.running = False
        self.core.handle_message({"source": "pet", "kind": "exit", "code": 0, "expected": None})
        self.assertFalse(self.config.get("enhanced_enabled"))
        self.core.handle_message({"kind": "control", "action": "manual-open"})
        self.assertTrue(self.config.get("enhanced_enabled"))
        self.assertTrue(self.config.get("auto_accompany"))
        self.assertTrue(self.pet.running)

    def test_auto_accompany_off_does_not_kill_current_pet(self):
        self.running = True
        self.core.tick_process()
        self.core.handle_message({"kind": "control", "action": "set-auto-accompany", "enabled": False})
        self.assertTrue(self.pet.running)
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        self.core.handle_message({"source": "pet", "kind": "farewell-complete"})
        self.running = True
        self.core.tick_process()
        self.assertFalse(self.pet.running)

    def test_hook_rechecks_process_and_applies_when_desktop_just_started(self):
        event = {
            "protocolVersion": 2,
            "event": "PreToolUse",
            "kind": "tool-start",
            "state": "WORKING",
            "message": "正在运行命令",
        }
        self.running = True
        self.core.handle_message(event)
        self.assertTrue(self.core.codex_running)
        self.assertTrue(self.pet.running)
        self.assertEqual(self.pet.sent[-1]["state"], "WORKING")
        self.assertTrue(self.config.get("hook_last_applied"))
        self.assertEqual(self.config.get("hook_ignored_count"), 0)
        self.assertIn("已接收并用于 Codex 桌宠", self.core.status_text())

    def test_bad_event_is_isolated_and_next_event_still_applies(self):
        calls = iter([False, True])
        def probe():
            value = next(calls)
            if not value:
                raise RuntimeError("probe")
            return value
        self.core.process_probe = probe
        event = {
            "protocolVersion": 2, "event": "PreToolUse", "kind": "tool-start",
            "state": "WORKING", "message": "工作",
        }
        self.core.handle_message(event)
        self.assertEqual(self.core.last_error, "event-RuntimeError")
        self.core.handle_message(event)
        self.assertTrue(self.core.codex_running)
        self.assertTrue(self.pet.running)

    def test_manual_show_resets_runtime_failure_lock(self):
        self.pet.restart_blocked = True
        self.pet.consecutive_failures = 5
        self.pet.reset_failure_lock = lambda: (
            setattr(self.pet, "restart_blocked", False),
            setattr(self.pet, "consecutive_failures", 0),
        )
        self.running = True
        self.core.handle_message({"kind": "control", "action": "show"})
        self.assertFalse(self.pet.restart_blocked)
        self.assertEqual(self.pet.consecutive_failures, 0)

    def test_all_hooks_are_audited_but_ignored_without_desktop_process(self):
        self.core.current_state = "WAITING"
        self.core.current_message = "保持原状态"
        self.core.current_agent_label = "Codex"
        self.core.active_tools.add(("session", "turn", "tool"))
        state_before = (
            self.core.current_state,
            self.core.current_message,
            self.core.current_agent_label,
            set(self.core.active_tools),
        )

        for event_name in sorted(ALLOWED_EVENTS):
            self.core.handle_message({
                "protocolVersion": 2,
                "event": event_name,
                "kind": "turn-stop" if event_name == "Stop" else "event",
                "state": "SUCCESS",
                "message": "不应应用",
                "modelSlug": "gpt-5.6-sol",
            })

        self.assertFalse(self.core.codex_running)
        self.assertFalse(self.pet.running)
        self.assertFalse(self.core.farewell_active)
        self.assertEqual(
            (
                self.core.current_state,
                self.core.current_message,
                self.core.current_agent_label,
                set(self.core.active_tools),
            ),
            state_before,
        )
        self.assertEqual(self.config.get("hook_event_count"), len(ALLOWED_EVENTS))
        self.assertEqual(self.config.get("hook_ignored_count"), len(ALLOWED_EVENTS))
        self.assertFalse(self.config.get("hook_last_applied"))
        self.assertIn("已收到但忽略", self.core.status_text())

    def test_parallel_tool_completion_keeps_working_until_last_tool(self):
        self.running = True
        self.core.tick_process()
        base = {"protocolVersion": 2, "event": "PreToolUse", "state": "WORKING", "message": "工作"}
        self.core.handle_message({**base, "kind": "tool-start", "toolUseId": "one"})
        self.core.handle_message({**base, "kind": "tool-start", "toolUseId": "two"})
        end = {"protocolVersion": 2, "event": "PostToolUse", "kind": "tool-end", "state": "THINKING", "message": "完成"}
        self.core.handle_message({**end, "toolUseId": "one", "failed": False})
        self.assertEqual(self.pet.sent[-1]["state"], "WORKING")
        self.core.handle_message({**end, "toolUseId": "two", "failed": False})
        self.assertEqual(self.pet.sent[-1]["state"], "THINKING")

    def test_pet_hide_request_persists_and_task_event_does_not_show_it(self):
        self.running = True
        self.core.tick_process()
        self.core.handle_message({"source": "pet", "protocolVersion": 1, "kind": "visibility", "visible": False})
        self.assertFalse(self.config.get("visible"))
        self.assertFalse(self.pet.sent[-1]["visible"])
        self.core.handle_message({
            "protocolVersion": 2,
            "event": "PreToolUse",
            "kind": "tool-start",
            "state": "WORKING",
            "message": "正在运行命令",
            "modelSlug": "gpt-5.6-sol",
        })
        self.assertFalse(self.pet.sent[-1]["visible"])
        self.assertEqual(self.pet.sent[-1]["agentLabel"], "GPT-5.6 Sol")

    def test_process_restart_resets_label_until_next_hook(self):
        self.running = True
        self.core.tick_process()
        self.core.handle_message({
            "protocolVersion": 2, "event": "SessionStart", "kind": "event",
            "state": "IDLE", "message": "已连接", "modelSlug": "gpt-5.6-terra",
        })
        self.assertEqual(self.core.current_agent_label, "GPT-5.6 Terra")
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        self.core.handle_message({"source": "pet", "kind": "farewell-complete"})
        self.running = True
        self.core.tick_process()
        self.assertEqual(self.core.current_agent_label, "Codex")

    def test_reopen_during_farewell_cancels_shutdown(self):
        self.running = True
        self.core.tick_process()
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        self.assertTrue(self.core.farewell_active)
        self.running = True
        self.core.tick_process()
        self.assertFalse(self.core.farewell_active)
        self.assertTrue(self.pet.running)
        self.assertIn("farewell-cancel", [item.get("kind") for item in self.pet.sent])

    def test_late_stop_after_confirmed_exit_does_not_cancel_farewell(self):
        self.running = True
        self.core.tick_process()
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        sent_before = len(self.pet.sent)
        self.core.handle_message({
            "protocolVersion": 2,
            "event": "Stop",
            "kind": "turn-stop",
            "state": "SUCCESS",
            "message": "本轮工作已完成",
            "modelSlug": "gpt-5.6-sol",
        })
        self.assertTrue(self.core.farewell_active)
        self.assertEqual(len(self.pet.sent), sent_before)
        self.assertEqual(self.config.get("hook_last_event"), "Stop")
        self.assertFalse(self.config.get("hook_last_applied"))

    def test_browser_session_start_cannot_cancel_farewell(self):
        self.running = True
        self.core.tick_process()
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        sent_before = len(self.pet.sent)

        self.core.handle_message({
            "protocolVersion": 2,
            "event": "SessionStart",
            "kind": "event",
            "state": "IDLE",
            "message": "Codex 已连接",
            "modelSlug": "gpt-5.6-luna",
        })

        self.assertTrue(self.core.farewell_active)
        self.assertTrue(self.core.codex_exit_confirmed)
        self.assertFalse(self.core.codex_running)
        self.assertEqual(len(self.pet.sent), sent_before)
        self.assertFalse(self.config.get("hook_last_applied"))

    def test_hidden_pet_skips_farewell(self):
        self.config.set("visible", False)
        self.running = True
        self.core.tick_process()
        self.running = False
        self.core.tick_process()
        self.core.tick_process()
        self.assertFalse(self.core.farewell_active)
        self.assertEqual(self.pet.stopped, ["codex-exit"])

    def test_farewell_controller_timeout_stops_stuck_runtime(self):
        self.running = True
        self.core.tick_process()
        self.running = False
        with patch("controller.core.time.monotonic", return_value=100.0):
            self.core.tick_process()
            self.core.tick_process()
        self.assertTrue(self.core.farewell_active)
        with patch("controller.core.time.monotonic", return_value=126.0):
            self.core.tick_pet()
        self.assertFalse(self.core.farewell_active)
        self.assertEqual(self.pet.stopped, ["codex-exit-timeout"])
        self.assertEqual(self.core.last_error, "farewell-timeout")


class ConfigMigrationTests(unittest.TestCase):
    def test_version_two_hook_status_migrates_as_previously_applied(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "controller.json"
            path.write_text(json.dumps({
                "version": 2,
                "hook_event_count": 9,
                "hook_last_event": "PostToolUse",
                "hook_last_received_at": 123,
            }), encoding="utf-8")

            config = ConfigStore(Path(temp))

            self.assertEqual(config.get("version"), 3)
            self.assertTrue(config.get("hook_last_applied"))
            self.assertEqual(config.get("hook_ignored_count"), 0)

    def test_version_three_hook_diagnostics_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "controller.json"
            path.write_text(json.dumps({
                "version": 3,
                "hook_last_applied": False,
                "hook_ignored_count": -7,
            }), encoding="utf-8")

            config = ConfigStore(Path(temp))

            self.assertFalse(config.get("hook_last_applied"))
            self.assertEqual(config.get("hook_ignored_count"), 0)


if __name__ == "__main__":
    unittest.main()
