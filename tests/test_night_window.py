from datetime import time

from despachoops_index.night_window import inside_window


def test_night_window_crosses_midnight():
    assert inside_window(time(23, 30), "23:00", "06:00")
    assert inside_window(time(3, 0), "23:00", "06:00")
    assert not inside_window(time(12, 0), "23:00", "06:00")
