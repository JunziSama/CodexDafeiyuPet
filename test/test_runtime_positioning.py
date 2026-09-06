from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from pet.config import Config  # noqa: E402
from pet.movement import target_y  # noqa: E402
from pet.menu_position import above_pet  # noqa: E402
from pet.snapping import Rect, clamp_offset, snap_offset  # noqa: E402


class FixedRandom:
    def __init__(self, roll=0.0, delta=30):
        self.roll = roll
        self.delta = delta
        self.calls = []

    def random(self):
        self.calls.append("random")
        return self.roll

    def randint(self, _low, _high):
        self.calls.append("randint")
        return self.delta


class MovementTests(unittest.TestCase):
    def test_horizontal_mode_never_changes_y_or_uses_rng(self):
        rnd = FixedRandom(roll=0.0, delta=75)
        self.assertEqual(target_y(True, 250, 0, 900, 120, 20, rnd), 250)
        self.assertEqual(rnd.calls, [])

    def test_normal_mode_can_wander_vertically(self):
        rnd = FixedRandom(roll=0.0, delta=30)
        self.assertEqual(target_y(False, 250, 0, 900, 120, 20, rnd), 280)
        self.assertEqual(rnd.calls, ["random", "randint"])


class MenuPositionTests(unittest.TestCase):
    def test_menu_is_centered_above_pet(self):
        self.assertEqual(
            above_pet((1600, 800, 160, 180), (320, 600), (0, 0, 1920, 1040)),
            (1520, 192),
        )

    def test_menu_falls_below_when_top_space_is_insufficient(self):
        self.assertEqual(
            above_pet((100, 20, 100, 100), (240, 300), (0, 0, 1920, 1040)),
            (30, 128),
        )


class SnapGeometryTests(unittest.TestCase):
    def test_snaps_independently_to_screen_corner(self):
        screen = Rect(0, 0, 1920, 1040)
        pet = Rect(8, 12, 108, 112)
        self.assertEqual(snap_offset(pet, screen, [], 20), (-8, -12))

    def test_snaps_outside_ordinary_window_with_axis_overlap(self):
        screen = Rect(0, 0, 1920, 1040)
        pet = Rect(610, 300, 710, 400)
        app = Rect(200, 100, 600, 700)
        self.assertEqual(snap_offset(pet, screen, [app], 20), (-10, 0))

    def test_window_without_other_axis_overlap_is_ignored(self):
        screen = Rect(0, 0, 1920, 1040)
        pet = Rect(610, 800, 710, 900)
        app = Rect(200, 100, 600, 700)
        self.assertEqual(snap_offset(pet, screen, [app], 20), (0, 0))

    def test_equal_distance_prefers_screen_edge(self):
        screen = Rect(0, 0, 1920, 1040)
        pet = Rect(10, 300, 110, 400)
        # screen-left delta=-10; window-right-to-pet-left delta=+10
        app = Rect(-200, 100, 20, 700)
        self.assertEqual(snap_offset(pet, screen, [app], 20)[0], -10)

    def test_clamp_keeps_visible_bounds_on_screen(self):
        self.assertEqual(
            clamp_offset(Rect(-5, 980, 95, 1080), Rect(0, 0, 1920, 1040)),
            (5, -40),
        )


class ConfigTests(unittest.TestCase):
    def test_exact_data_dir_override_ignores_inherited_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            exact = Path(directory) / "canonical"
            appcontainer = Path(directory) / "appcontainer"
            with patch.dict(os.environ, {
                "DSH_PET_DATA_DIR": str(exact),
                "APPDATA": str(appcontainer),
            }, clear=False):
                cfg = Config()
                cfg.set("movement_frequency", "off")
                cfg.save()
            self.assertEqual(cfg.dir, exact)
            self.assertTrue((exact / "config.json").is_file())
            self.assertFalse((appcontainer / "dsh-pet-standalone" / "config.json").exists())

    def test_positioning_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = Config(base=Path(directory))
            self.assertFalse(cfg.get("horizontal_auto_move_only"))
            self.assertFalse(cfg.get("window_snap_enabled"))
            self.assertEqual(cfg.get("window_snap_distance"), 20)
            cfg.set("horizontal_auto_move_only", True)
            cfg.set("window_snap_enabled", True)
            cfg.set("window_snap_distance", 35)
            cfg.save()

            loaded = Config(base=Path(directory))
            self.assertTrue(loaded.get("horizontal_auto_move_only"))
            self.assertTrue(loaded.get("window_snap_enabled"))
            self.assertEqual(loaded.get("window_snap_distance"), 35)
            raw = json.loads(loaded.path.read_text(encoding="utf-8"))
            self.assertIn("horizontal_auto_move_only", raw)
            self.assertIn("window_snap_enabled", raw)

    def test_v5_frequency_defaults_and_legacy_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config_dir = base / "dsh-pet-standalone"
            config_dir.mkdir(parents=True)
            (config_dir / "config.json").write_text(json.dumps({
                "version": 3,
                "animation_gap_seconds": 120,
                "no_move": True,
                "horizontal_auto_move_only": True,
            }), encoding="utf-8")
            loaded = Config(base=base)
            self.assertEqual(loaded.get("version"), 5)
            self.assertEqual(loaded.get("idle_animation_frequency"), "occasional")
            self.assertEqual(loaded.get("movement_frequency"), "off")
            self.assertTrue(loaded.get("horizontal_auto_move_only"))
            self.assertEqual(loaded.get("exit_animation_mode"), "farewell_only")

    def test_exit_animation_mode_persists_and_invalid_value_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cfg = Config(base=base)
            cfg.set("exit_animation_mode", "bubble_sync")
            cfg.save()
            self.assertEqual(Config(base=base).get("exit_animation_mode"), "bubble_sync")

            cfg.set("exit_animation_mode", "unsafe-value")
            cfg.save()
            self.assertEqual(Config(base=base).get("exit_animation_mode"), "farewell_only")

    def test_legacy_gap_levels_map_to_named_frequencies(self):
        cases = ((0, "continuous"), (15, "frequent"), (45, "balanced"), (120, "occasional"))
        for gap, expected in cases:
            with self.subTest(gap=gap), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                config_dir = base / "dsh-pet-standalone"
                config_dir.mkdir(parents=True)
                (config_dir / "config.json").write_text(json.dumps({
                    "version": 3, "animation_gap_seconds": gap,
                }), encoding="utf-8")
                self.assertEqual(Config(base=base).get("idle_animation_frequency"), expected)


if __name__ == "__main__":
    unittest.main()
