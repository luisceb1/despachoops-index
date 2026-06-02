from __future__ import annotations

import sys


def user_idle_minutes(required: int) -> bool:
    if required <= 0:
        return True
    if sys.platform != "win32":
        return True
    return _windows_idle_minutes() >= required


def _windows_idle_minutes() -> float:
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 60000.0
