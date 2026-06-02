from __future__ import annotations

from datetime import datetime, time


def parse_hhmm(value: str) -> time:
    hour, minute = [int(p) for p in value.strip().split(":", 1)]
    return time(hour, minute)


def inside_window(current: time, start: str, end: str) -> bool:
    s, e = parse_hhmm(start), parse_hhmm(end)
    if s <= e:
        return s <= current <= e
    return current >= s or current <= e


def can_run_now(config, *, idle_ok: bool, now: datetime | None = None) -> tuple[bool, str]:
    current = now or datetime.now()
    if not inside_window(current.time(), config.night_window_start, config.night_window_end):
        return False, (
            f"Fuera de ventana {config.night_window_start}-{config.night_window_end}; "
            f"hora {current.strftime('%H:%M')}"
        )
    if config.require_idle_minutes > 0 and not idle_ok:
        return False, f"Usuario activo (< {config.require_idle_minutes} min idle)"
    return True, "OK"
