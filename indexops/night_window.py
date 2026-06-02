from __future__ import annotations

from datetime import datetime, time


def parse_hhmm(value: str) -> time:
    hour, minute = [int(part) for part in value.strip().split(":", 1)]
    return time(hour, minute)


def inside_night_window(
    current: time,
    start_value: str,
    end_value: str,
) -> bool:
    """
    Ventana nocturna, p. ej. 23:00–06:00 (cruza medianoche).
    Si start <= end, ventana dentro del mismo día.
    """
    start = parse_hhmm(start_value)
    end = parse_hhmm(end_value)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def can_run_now(
    config,
    now: datetime | None = None,
    *,
    idle_ok: bool = True,
) -> tuple[bool, str]:
    current = now or datetime.now()
    if not inside_night_window(
        current.time(),
        config.night_window_start,
        config.night_window_end,
    ):
        return (
            False,
            f"Fuera de ventana ({config.night_window_start}–{config.night_window_end}); "
            f"hora actual {current.strftime('%H:%M')}",
        )
    if config.require_idle_minutes > 0 and not idle_ok:
        return (
            False,
            f"Usuario activo (requiere {config.require_idle_minutes} min sin input)",
        )
    return True, "OK"
