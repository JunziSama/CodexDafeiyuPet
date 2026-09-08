from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from pet.frame_cache import ByteBudgetLru  # noqa: E402
from pet.library import MovieLibrary  # noqa: E402
from pet.webm_clip import _FFMPEG_INPUT_PARAMS  # noqa: E402


class CacheBudgetTests(unittest.TestCase):
    def test_lru_never_exceeds_budget(self):
        cache = ByteBudgetLru(10)
        cache.put("a", object(), 6)
        cache.put("b", object(), 6)
        self.assertLessEqual(cache.total_bytes(), 10)
        self.assertNotIn("a", cache)
        self.assertIn("b", cache)

    def test_recently_read_entry_survives_eviction(self):
        cache = ByteBudgetLru(12)
        cache.put("a", 1, 4)
        cache.put("b", 2, 4)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3, 6)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)

    def test_oversized_entry_is_not_cached(self):
        cache = ByteBudgetLru(8)
        cache.put("large", object(), 9)
        self.assertEqual(len(cache), 0)
        self.assertEqual(cache.total_bytes(), 0)


class DecoderPolicyTests(unittest.TestCase):
    def test_ffmpeg_is_limited_to_one_thread(self):
        args = list(_FFMPEG_INPUT_PARAMS)
        index = args.index("-threads")
        self.assertEqual(args[index + 1], "1")

    def test_movie_library_is_lazy_and_hidden_prewarm_is_inert(self):
        app = QApplication.instance() or QApplication([])
        asset_dir = RUNTIME / "assets" / "characters" / "shenshen" / "videos"
        library = MovieLibrary(asset_dir=asset_dir, prewarm_enabled=True)
        try:
            initial = set(library.movies())
            self.assertLess(len(initial), len(library.names()))
            name = next(item for item in library.names() if item not in initial)
            library.pause_warm()
            library.warm_predicted(name)
            app.processEvents()
            self.assertEqual(set(library.movies()), initial)
            library.resume_warm()
            library.movie(name)
            self.assertEqual(len(library.movies()), len(initial) + 1)
        finally:
            library.cleanup()


if __name__ == "__main__":
    unittest.main()
