from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from pet.glove_cursor import GloveCursorFilter, load_native_cursor  # noqa: E402


class FakeWidget:
    def __init__(self):
        self.cursors = []

    def setCursor(self, cursor):
        self.cursors.append(cursor)


class GloveCursorTests(unittest.TestCase):
    def test_cursor_assets_match_chromium_upstream(self):
        assets = ROOT / "runtime" / "assets" / "cursors"
        expected = {
            "cursor_grab.cur": "3f37213b8c0a7374308b2ae99d4eefa2",
            "cursor_grabbing.cur": "8605cf2c21985f59d2480da72aebe3aa",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.md5((assets / name).read_bytes()).hexdigest(), digest)

    def test_non_windows_load_falls_back(self):
        with patch("pet.glove_cursor.sys.platform", "linux"):
            self.assertIsNone(load_native_cursor(Path("missing.cur")))

    def test_qt_fallback_tracks_press_state(self):
        widget = FakeWidget()
        cursor_filter = GloveCursorFilter(widget)
        cursor_filter.set_pressed(True)
        cursor_filter.set_pressed(False)
        self.assertEqual(len(widget.cursors), 2)


if __name__ == "__main__":
    unittest.main()
