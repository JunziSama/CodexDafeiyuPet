"""Native Windows glove cursor with a safe Qt fallback."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QPoint, Qt


def _cursor_api():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    load_file = user32.LoadCursorFromFileW
    load_file.argtypes = [wintypes.LPCWSTR]
    load_file.restype = wintypes.HANDLE
    set_cursor = user32.SetCursor
    set_cursor.argtypes = [wintypes.HANDLE]
    set_cursor.restype = wintypes.HANDLE
    return load_file, set_cursor


def load_native_cursor(path: Path) -> Any:
    if sys.platform != "win32":
        return None
    try:
        return _cursor_api()[0](str(path)) or None
    except Exception:
        return None


class GloveCursorFilter(QAbstractNativeEventFilter):
    WM_SETCURSOR = 0x0020
    HTCLIENT = 1

    def __init__(self, widget, open_handle=None, closed_handle=None) -> None:
        super().__init__()
        self.widget = widget
        self.open_handle = open_handle
        self.closed_handle = closed_handle
        self.pressed = False

    @property
    def native_available(self) -> bool:
        return bool(self.open_handle and self.closed_handle and sys.platform == "win32")

    def set_pressed(self, pressed: bool) -> None:
        self.pressed = bool(pressed)
        if not self.native_available:
            self.widget.setCursor(
                Qt.CursorShape.ClosedHandCursor if self.pressed else Qt.CursorShape.OpenHandCursor
            )
            return
        try:
            _cursor_api()[1](self.closed_handle if self.pressed else self.open_handle)
        except Exception:
            pass

    def _inside_character(self, global_x: int, global_y: int) -> bool:
        local = self.widget.mapFromGlobal(QPoint(global_x, global_y))
        return bool(self.widget.rect().contains(local) and self.widget._is_in_interactive_area(local))

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if not self.native_available:
            return False, 0
        try:
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message != self.WM_SETCURSOR or int(msg.hWnd or 0) != int(self.widget.winId()):
                return False, 0
            if (int(msg.lParam) & 0xFFFF) != self.HTCLIENT:
                return False, 0
            point = wintypes.POINT()
            if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return False, 0
            if not self._inside_character(point.x, point.y):
                return False, 0
            _cursor_api()[1](self.closed_handle if self.pressed else self.open_handle)
            return True, 0
        except Exception:
            return False, 0


def install_glove_cursor(app, widget, asset_dir: Path):
    open_handle = load_native_cursor(asset_dir / "cursor_grab.cur")
    closed_handle = load_native_cursor(asset_dir / "cursor_grabbing.cur")
    cursor_filter = GloveCursorFilter(widget, open_handle, closed_handle)
    if cursor_filter.native_available:
        app.installNativeEventFilter(cursor_filter)
    else:
        widget.setCursor(Qt.CursorShape.OpenHandCursor)
    return cursor_filter
