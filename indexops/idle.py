from __future__ import annotations

import sys


def user_idle_minutes(required_minutes: int) -> bool:
    """
    True si el usuario lleva al menos required_minutes sin input.
    En macOS/Linux sin API fiable devuelve True (no bloquea).
    """
    if required_minutes <= 0:
        return True
    if sys.platform != "win32":
        return True
    return _windows_idle_minutes() >= required_minutes


def _windows_idle_minutes() -> float:
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis / 60000.0
