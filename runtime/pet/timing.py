"""Refresh-rate and stable physics timing helpers."""
from __future__ import annotations

import math


def smooth_interval_ms(refresh_rate: float | int | None) -> int:
    try:
        rate = float(refresh_rate or 0.0)
    except (TypeError, ValueError):
        rate = 0.0
    if rate <= 90.0:
        return 16
    return max(5, min(16, int(round(1000.0 / rate))))


def physics_substeps(elapsed: float, *, max_elapsed: float = 0.05, max_step: float = 1 / 120) -> list[float]:
    dt = max(0.0, min(float(elapsed), max_elapsed))
    if dt <= 0.0:
        return []
    count = max(1, int(math.ceil(dt / max_step)))
    return [dt / count] * count
