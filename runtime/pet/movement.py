"""Pure autonomous movement decisions, separated for deterministic tests."""
from __future__ import annotations

import random


def wander_target_y(start_y: float, top: float, bottom: float, height: float,
                    margin: float, rnd=random) -> int:
    y_lo = top + margin
    y_hi = bottom - height - margin
    if y_hi <= y_lo:
        return int(start_y)
    max_dy = max(40, int((y_hi - y_lo) * 0.25))
    dy = rnd.randint(-max_dy, max_dy)
    return int(max(y_lo, min(y_hi, start_y + dy)))


def target_y(horizontal_only: bool, start_y: float, top: float, bottom: float,
             height: float, margin: float, rnd=random) -> int:
    """Choose a walk destination y; drag and throw paths never call this."""
    if horizontal_only or rnd.random() >= 0.55:
        return int(start_y)
    return wander_target_y(start_y, top, bottom, height, margin, rnd=rnd)
