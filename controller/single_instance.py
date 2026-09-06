from __future__ import annotations

import ctypes
import os


ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = r"Local\DafeiyuCodexCompanion.Controller"


class InstanceMutex:
    """Own a per-user Windows mutex for the resident tray controller."""

    def __init__(self, handle: int | None, acquired: bool) -> None:
        self.handle = handle
        self.acquired = acquired

    @classmethod
    def acquire(cls, name: str = DEFAULT_MUTEX_NAME) -> "InstanceMutex":
        if os.name != "nt":
            return cls(None, True)

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return cls(None, False)
        return cls(int(handle), True)

    def close(self) -> None:
        if self.handle is None or os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.CloseHandle(self.handle)
        self.handle = None

