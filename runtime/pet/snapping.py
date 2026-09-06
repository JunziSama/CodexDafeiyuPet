# -*- coding: utf-8 -*-
"""Pure snapping geometry plus Win32 top-level-window discovery.

All public geometry uses Qt-style logical pixels and half-open rectangles.  The
Win32 adapter converts physical window bounds into the logical coordinate space
of the corresponding QScreen before returning them.
"""
from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    @property
    def area(self) -> float:
        return self.width * self.height

    def translated(self, dx: float, dy: float) -> "Rect":
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)

    def intersects(self, other: "Rect") -> bool:
        return _overlap(self.left, self.right, other.left, other.right) and _overlap(
            self.top, self.bottom, other.top, other.bottom
        )

    def intersection_area(self, other: "Rect") -> float:
        return max(0.0, min(self.right, other.right) - max(self.left, other.left)) * max(
            0.0, min(self.bottom, other.bottom) - max(self.top, other.top)
        )


@dataclass(frozen=True)
class ScreenSpace:
    """Mapping between one Windows monitor and its Qt logical geometry."""

    name: str
    logical: Rect
    physical: Rect
    dpr: float = 1.0


SHELL_WINDOW_CLASSES = frozenset({
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
    "XamlExplorerHostIslandWindow",
    "Windows.UI.Composition.DesktopWindowContentBridge",
})


def _overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return min(a1, b1) > max(a0, b0)


def _choose(candidates: list[tuple[float, int, float, float]]) -> float:
    """Return delta from (distance, source priority, area tie-break, delta)."""
    if not candidates:
        return 0.0
    return min(candidates, key=lambda item: (item[0], item[1], item[2]))[3]


def snap_offset(
    pet: Rect,
    screen: Rect,
    windows: Iterable[Rect],
    threshold: float = 20.0,
) -> tuple[float, float]:
    """Return nearest independent x/y edge-snap offsets.

    Screen edges place the pet inside the work area.  Window edges place the
    pet immediately outside an ordinary window.  Candidates require overlap on
    the other axis.  Equal-distance ties prefer the screen, then the window
    with the greatest visible area.
    """
    threshold = max(0.0, float(threshold))
    x_candidates: list[tuple[float, int, float, float]] = []
    y_candidates: list[tuple[float, int, float, float]] = []

    if _overlap(pet.top, pet.bottom, screen.top, screen.bottom):
        for delta in (screen.left - pet.left, screen.right - pet.right):
            if abs(delta) <= threshold:
                x_candidates.append((abs(delta), 0, -screen.area, delta))
    if _overlap(pet.left, pet.right, screen.left, screen.right):
        for delta in (screen.top - pet.top, screen.bottom - pet.bottom):
            if abs(delta) <= threshold:
                y_candidates.append((abs(delta), 0, -screen.area, delta))

    for window in windows:
        if not window.intersects(screen):
            continue
        visible_area = window.intersection_area(screen)
        if _overlap(pet.top, pet.bottom, window.top, window.bottom):
            for delta in (window.left - pet.right, window.right - pet.left):
                if abs(delta) <= threshold:
                    x_candidates.append((abs(delta), 1, -visible_area, delta))
        if _overlap(pet.left, pet.right, window.left, window.right):
            for delta in (window.top - pet.bottom, window.bottom - pet.top):
                if abs(delta) <= threshold:
                    y_candidates.append((abs(delta), 1, -visible_area, delta))

    return _choose(x_candidates), _choose(y_candidates)


def clamp_offset(pet: Rect, screen: Rect) -> tuple[float, float]:
    """Return the smallest offset that keeps visible pet bounds on-screen."""
    if pet.width > screen.width:
        dx = screen.left - pet.left
    elif pet.left < screen.left:
        dx = screen.left - pet.left
    elif pet.right > screen.right:
        dx = screen.right - pet.right
    else:
        dx = 0.0
    if pet.height > screen.height:
        dy = screen.top - pet.top
    elif pet.top < screen.top:
        dy = screen.top - pet.top
    elif pet.bottom > screen.bottom:
        dy = screen.bottom - pet.bottom
    else:
        dy = 0.0
    return dx, dy


def _logical_rect(raw: Rect, screen: ScreenSpace) -> Rect:
    dpr = max(0.01, float(screen.dpr or 1.0))
    return Rect(
        screen.logical.left + (raw.left - screen.physical.left) / dpr,
        screen.logical.top + (raw.top - screen.physical.top) / dpr,
        screen.logical.left + (raw.right - screen.physical.left) / dpr,
        screen.logical.top + (raw.bottom - screen.physical.top) / dpr,
    )


def screen_spaces(qscreens: Iterable[object]) -> list[ScreenSpace]:
    """Build physical/logical mappings from QScreen-like objects."""
    qscreens = list(qscreens)
    physical_by_name: dict[str, Rect] = {}
    if sys.platform == "win32":
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        MONITORINFOF_PRIMARY = 1

        class WINRECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", WINRECT),
                        ("rcWork", WINRECT), ("dwFlags", wintypes.DWORD),
                        ("szDevice", wintypes.WCHAR * 32)]

        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
            ctypes.POINTER(WINRECT), wintypes.LPARAM
        )

        @callback_type
        def callback(monitor, _hdc, _rect, _lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(info)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                rect = info.rcMonitor
                physical_by_name[str(info.szDevice)] = Rect(
                    rect.left, rect.top, rect.right, rect.bottom
                )
            return True

        try:
            user32.EnumDisplayMonitors(None, None, callback, 0)
        except Exception:
            physical_by_name.clear()

    result = []
    for qscreen in qscreens:
        geometry = qscreen.geometry()
        logical = Rect(
            float(geometry.x()), float(geometry.y()),
            float(geometry.x() + geometry.width()),
            float(geometry.y() + geometry.height()),
        )
        dpr = max(0.01, float(qscreen.devicePixelRatio() or 1.0))
        name = str(qscreen.name())
        physical = physical_by_name.get(name)
        if physical is None:
            physical = Rect(
                logical.left * dpr, logical.top * dpr,
                logical.right * dpr, logical.bottom * dpr,
            )
        result.append(ScreenSpace(name, logical, physical, dpr))
    return result


def enumerate_ordinary_windows(
    screens: Iterable[ScreenSpace],
    own_pid: int | None = None,
    excluded_hwnds: Iterable[int] = (),
) -> list[Rect]:
    """Enumerate visible, ordinary Win32 top-level windows in logical pixels."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes

    spaces = list(screens)
    if not spaces:
        return []
    own_pid = os.getpid() if own_pid is None else int(own_pid)
    excluded = {int(value) for value in excluded_hwnds}
    user32 = ctypes.windll.user32
    try:
        dwmapi = ctypes.windll.dwmapi
    except OSError:
        dwmapi = None

    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TRANSPARENT = 0x00000020
    DWMWA_CLOAKED = 14
    DWMWA_EXTENDED_FRAME_BOUNDS = 9

    class WINRECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    def raw_rect(hwnd) -> Rect | None:
        value = WINRECT()
        ok = False
        if dwmapi is not None:
            ok = dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0
        if not ok:
            ok = bool(user32.GetWindowRect(hwnd, ctypes.byref(value)))
        if not ok or value.right <= value.left or value.bottom <= value.top:
            return None
        return Rect(value.left, value.top, value.right, value.bottom)

    def matching_screen(rect: Rect) -> ScreenSpace:
        cx, cy = (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2
        containing = [s for s in spaces if s.physical.left <= cx < s.physical.right
                      and s.physical.top <= cy < s.physical.bottom]
        if containing:
            return containing[0]
        return min(spaces, key=lambda s: abs(cx - (s.physical.left + s.physical.right) / 2)
                   + abs(cy - (s.physical.top + s.physical.bottom) / 2))

    result: list[Rect] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd, _lparam):
        try:
            value = int(hwnd)
            if value in excluded or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if int(pid.value) == own_pid:
                return True
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value in SHELL_WINDOW_CLASSES:
                return True
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            if style & (WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT):
                return True
            if dwmapi is not None:
                cloaked = wintypes.DWORD()
                if dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                ) == 0 and cloaked.value:
                    return True
            raw = raw_rect(hwnd)
            if raw is not None:
                result.append(_logical_rect(raw, matching_screen(raw)))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    return result
