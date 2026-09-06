from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME / "vendor"))
sys.path.insert(0, str(RUNTIME))

from eac_entry import AnimationScheduler, EacPetController  # noqa: E402
from pet import catalog  # noqa: E402


class FakeWindow:
    def __init__(self, animation: str) -> None:
        self.anim = animation
        self._dragging = False
        self.played: list[str] = []
        self.origins: list[str] = []
        self.bubbles: list[tuple] = []
        self.interactions_locked = False
        self.playback_speed = 1.4
        self.exit_animation_mode = "current_then_farewell"
        self.movie = None
        self.hold_count = 0
        self.hide_count = 0
        self.show_count = 0
        self.interrupt_count = 0
        self.idle = "待机呼吸休闲"
        self.idles = [self.idle]
        self.turns = ["东张西望"]
        self.acts = ["写代码"]
        self.moves = ["螃蟹走路"]
        self.move_probability = 0.0
        self.idle_due = False
        self.move_attempts = 0

    def show(self):
        self.show_count += 1

    def raise_(self):
        pass

    def hide(self):
        self.hide_count += 1

    def show_bubble(self, *args, **kwargs):
        self.bubbles.append((args, kwargs))

    def _switch(self, name: str, origin="idle") -> None:
        self.anim = name
        self.played.append(name)
        self.origins.append(origin)

    def set_interactions_locked(self, locked):
        self.interactions_locked = bool(locked)

    def hold_finished_animation(self):
        self.hold_count += 1

    def interrupt_current_animation(self):
        self.interrupt_count += 1

    def movement_probability(self):
        return self.move_probability

    def idle_action_due(self, _now):
        return self.idle_due

    def mark_idle_action(self, _now):
        self.idle_due = False

    def _try_move_with_turnaround(self, origin="movement"):
        self.move_attempts += 1
        if self.move_probability > 0:
            self._switch(self.moves[0], origin=origin)
            return True
        return False


class FakeTimer:
    def __init__(self):
        self.active = False
        self.interval = 0

    def start(self, interval):
        self.active = True
        self.interval = interval

    def stop(self):
        self.active = False


class CompleteClipSchedulingTests(unittest.TestCase):
    def make_controller(self) -> EacPetController:
        controller = EacPetController.__new__(EacPetController)
        controller.window = FakeWindow("写代码")
        controller.visible = True
        controller.names = [
            "待机呼吸休闲", "东张西望", "螃蟹走路", "写代码",
            "点击回应 - 开心跃动", "点击回应 - 元气挥手",
        ]
        controller.scheduler = AnimationScheduler(controller.names)
        controller.current_state = "WORKING"
        controller.current_animation = "写代码"
        controller.current_origin = "controller"
        controller.playing_state = "WORKING"
        controller.last_pick_at = 0.0
        controller.pick_phase = "default"
        controller.last_message = ""
        controller.agent_label = "Codex"
        controller.farewell_requested = False
        controller.farewell_phase = ""
        controller.farewell_animation = ""
        controller.farewell_mode = "farewell_only"
        controller.farewell_current_finished = False
        controller.farewell_window_hidden = False
        controller._pre_farewell_speed = None
        controller._farewell_wait_timer = FakeTimer()
        controller._farewell_animation_timer = FakeTimer()
        return controller

    def test_state_change_waits_for_current_clip_completion(self):
        controller = self.make_controller()
        controller.apply_state({"state": "SUCCESS", "message": "完成"})
        self.assertEqual(controller.current_state, "SUCCESS")
        self.assertEqual(controller.window.played, [])

        controller._on_animation_finished("写代码")
        self.assertEqual(len(controller.window.played), 1)
        self.assertIn(controller.window.played[0], {
            "点击回应 - 开心跃动", "点击回应 - 元气挥手",
        })
        success_name = controller.current_animation
        controller._on_animation_finished(success_name)
        self.assertEqual(controller.current_state, "IDLE")
        self.assertEqual(controller.current_animation, "待机呼吸休闲")

    def test_repeated_state_only_updates_bubble(self):
        controller = self.make_controller()
        controller.apply_state({"state": "WORKING", "message": "继续处理"})
        self.assertEqual(controller.window.played, [])

    def test_click_animation_is_authoritative_until_complete(self):
        controller = self.make_controller()
        click = "点击回应 - 开心跃动"
        controller.window.anim = click
        controller._on_animation_started(click, "click")
        controller.apply_state({"state": "WORKING", "message": "正在执行"})
        controller.apply_state({"state": "SUCCESS", "message": "完成"})
        self.assertEqual(controller.window.played, [])
        self.assertEqual(controller.current_state, "SUCCESS")

        controller._on_animation_finished(click)
        self.assertEqual(len(controller.window.played), 1)
        self.assertIn(controller.window.played[0], {
            "点击回应 - 开心跃动", "点击回应 - 元气挥手",
        })
        self.assertEqual(controller.window.origins[-1], "controller")

    def test_menu_animation_is_not_replaced_by_repeated_hook(self):
        controller = self.make_controller()
        controller.window.anim = "东张西望"
        controller._on_animation_started("东张西望", "menu")
        controller.apply_state({"state": "WORKING", "message": "一步"})
        controller.apply_state({"state": "WORKING", "message": "两步"})
        self.assertEqual(controller.window.played, [])
        controller._on_animation_finished("东张西望")
        self.assertEqual(controller.window.origins[-1], "controller")

    def test_scheduler_resolves_display_names_with_spaces(self):
        scheduler = AnimationScheduler(["点击回应-元气挥手"])
        self.assertEqual(scheduler.available(["点击回应 - 元气挥手"]), ["点击回应-元气挥手"])

    def test_shenshen_folder_categories_keep_five_clicks_and_eighty_randoms(self):
        asset_dir = RUNTIME / "assets" / "characters" / "shenshen" / "videos"
        files = sorted(asset_dir.rglob("*.webm"))
        names = [path.stem for path in files]
        folder_files: dict[str, list[str]] = {}
        folder_map: dict[str, str] = {}
        for path in files:
            folder = path.relative_to(asset_dir).parts[0].lower()
            folder_map[path.stem] = folder
            folder_files.setdefault(folder, []).append(path.stem)
        cats = catalog.build_categories(names, folder_map=folder_map, folder_files=folder_files)
        self.assertEqual(len(cats["clicks"]), 5)
        self.assertEqual(len(folder_files["random"]), 80)
        self.assertTrue(all(name.startswith("点击回应-") for name in cats["clicks"]))

    def test_farewell_waits_for_click_then_completes(self):
        controller = self.make_controller()
        controller.names.remove("点击回应 - 元气挥手")
        controller.names.append("点击回应-元气挥手")
        controller.scheduler = AnimationScheduler(controller.names)
        controller.window.anim = "点击回应 - 开心跃动"
        controller._on_animation_started("点击回应 - 开心跃动", "click")
        controller.begin_farewell({"animation": "点击回应 - 元气挥手"})
        self.assertEqual(controller.farewell_phase, "waiting")
        self.assertTrue(controller.window.interactions_locked)
        self.assertEqual(controller.window.played, [])

        controller._on_animation_finished("点击回应 - 开心跃动")
        self.assertEqual(controller.farewell_phase, "playing")
        self.assertEqual(controller.window.played[-1], "点击回应-元气挥手")
        self.assertEqual(controller.window.origins[-1], "farewell")
        self.assertEqual(controller.window.playback_speed, 1.0)
        with patch("builtins.print") as output:
            controller._on_animation_finished("点击回应-元气挥手")
        self.assertEqual(controller.farewell_phase, "complete")
        output.assert_called_once()

    def test_farewell_cancel_restores_speed_and_interactions(self):
        controller = self.make_controller()
        controller.window.exit_animation_mode = "farewell_only"
        controller.names.remove("点击回应 - 元气挥手")
        controller.names.append("点击回应-元气挥手")
        controller.scheduler = AnimationScheduler(controller.names)
        controller.begin_farewell({"animation": "点击回应 - 元气挥手"})
        self.assertEqual(controller.farewell_phase, "playing")
        self.assertEqual(controller.window.playback_speed, 1.0)
        controller.cancel_farewell()
        self.assertFalse(controller.farewell_requested)
        self.assertFalse(controller.window.interactions_locked)
        self.assertEqual(controller.window.playback_speed, 1.4)
        self.assertEqual(controller.window.origins[-1], "idle")

    def test_farewell_only_interrupts_current_and_finishes_after_wave(self):
        controller = self.make_controller()
        controller.window.exit_animation_mode = "farewell_only"
        controller.begin_farewell({"animation": "点击回应 - 元气挥手"})
        self.assertEqual(controller.farewell_phase, "playing")
        self.assertEqual(controller.window.origins[-1], "farewell")
        self.assertEqual(controller.window.playback_speed, 1.0)
        with patch("builtins.print") as output:
            controller._on_animation_finished(controller.current_animation)
        self.assertEqual(controller.farewell_phase, "complete")
        output.assert_called_once()

    def test_current_only_finishes_current_clip_without_wave(self):
        controller = self.make_controller()
        controller.window.exit_animation_mode = "current_only"
        controller.begin_farewell({"animation": "点击回应 - 元气挥手"})
        self.assertEqual(controller.farewell_phase, "waiting")
        self.assertEqual(controller.window.played, [])
        with patch("builtins.print") as output:
            controller._on_animation_finished("写代码")
        self.assertEqual(controller.farewell_phase, "complete")
        self.assertNotIn("farewell", controller.window.origins)
        output.assert_called_once()

    def test_bubble_sync_waits_for_real_dismissal_and_hides_window(self):
        controller = self.make_controller()
        controller.window.exit_animation_mode = "bubble_sync"
        controller.begin_farewell({"bubbleDurationMs": 6000})
        self.assertEqual(controller.farewell_phase, "waiting_bubble")
        self.assertEqual(controller._farewell_wait_timer.interval, 6250)
        controller._on_animation_finished("写代码")
        self.assertTrue(controller.farewell_current_finished)
        self.assertEqual(controller.window.hold_count, 1)
        with patch("builtins.print") as output:
            controller._on_bubble_dismissed()
        self.assertEqual(controller.farewell_phase, "complete")
        self.assertEqual(controller.window.hide_count, 1)
        self.assertEqual(controller.window.interrupt_count, 1)
        output.assert_called_once()

    def test_bubble_sync_cancel_after_clip_end_resumes_idle(self):
        controller = self.make_controller()
        controller.window.exit_animation_mode = "bubble_sync"
        controller.begin_farewell({"bubbleDurationMs": 6000})
        controller._on_animation_finished("写代码")
        controller.cancel_farewell()
        self.assertFalse(controller.window.interactions_locked)
        self.assertEqual(controller.window.origins[-1], "idle")

    def test_idle_movement_probability_is_independent_from_idle_actions(self):
        controller = self.make_controller()
        controller.current_state = "IDLE"
        controller.playing_state = "IDLE"
        controller.current_animation = "待机呼吸休闲"
        controller.window.anim = "待机呼吸休闲"
        controller.window.move_probability = 0.3
        controller.window.idle_due = False
        with patch("eac_entry.random.random", return_value=0.0):
            controller._on_animation_finished("待机呼吸休闲")
        self.assertEqual(controller.window.move_attempts, 1)
        self.assertEqual(controller.current_animation, "螃蟹走路")


if __name__ == "__main__":
    unittest.main()
