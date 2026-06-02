from datetime import datetime, time

from indexops.night_window import inside_night_window, parse_hhmm


def test_window_crosses_midnight():
    assert inside_night_window(time(23, 30), "23:00", "06:00")
    assert inside_night_window(time(3, 0), "23:00", "06:00")
    assert not inside_night_window(time(12, 0), "23:00", "06:00")
    assert not inside_night_window(time(22, 59), "23:00", "06:00")


def test_same_day_window():
    assert inside_night_window(time(1, 0), "00:00", "05:00")
    assert not inside_night_window(time(6, 0), "00:00", "05:00")


def test_parse_hhmm():
    assert parse_hhmm("23:00") == time(23, 0)
