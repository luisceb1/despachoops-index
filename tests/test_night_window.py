from datetime import datetime, time
from pathlib import Path

from despachoops_index.config import AppConfig, LlmConfig
from despachoops_index.night_window import can_run_now, inside_window, parse_hhmm


def _minimal_config(**kwargs) -> AppConfig:
    base = dict(
        scan_root=Path("."),
        data_dir=Path("data"),
        index_db_path=Path("data/db.sqlite"),
        log_dir=Path("data/logs"),
        ocr_cache_dir=Path("data/ocr"),
        ocr_queue_path=Path("data/ocr.csv"),
        worker_lock_path=Path("data/lock"),
        recursive=True,
        max_files_per_index_run=100,
        max_files_per_ocr_run=10,
        catalog_each_night_cycle=False,
        index_text_enabled=True,
        index_skip_large_files_mb=80,
        ocr_skip_large_files_mb=120,
        ocr_worker_enabled=True,
        ocr_max_pages_per_file=5,
        ocr_languages="spa",
        night_window_start="23:00",
        night_window_end="06:00",
        require_idle_minutes=0,
        exclude_dirs=(),
        exclude_patterns=(),
        exclude_path_patterns=(),
        exclude_extensions=(),
        llm=LlmConfig(),
        worker_enabled=True,
        worker_interval_seconds=600,
        worker_stale_lock_minutes=180,
    )
    base.update(kwargs)
    return AppConfig(**base)


def test_parse_hhmm():
    assert parse_hhmm("23:00") == time(23, 0)


def test_night_window_crosses_midnight():
    assert inside_window(time(23, 30), "23:00", "06:00")
    assert inside_window(time(3, 0), "23:00", "06:00")
    assert not inside_window(time(12, 0), "23:00", "06:00")


def test_can_run_now_inside_window():
    cfg = _minimal_config(require_idle_minutes=0)
    ok, _ = can_run_now(cfg, idle_ok=True, now=datetime(2026, 6, 2, 2, 0))
    assert ok


def test_can_run_now_outside_window():
    cfg = _minimal_config()
    ok, reason = can_run_now(cfg, idle_ok=True, now=datetime(2026, 6, 2, 12, 0))
    assert not ok
    assert "Fuera" in reason or "ventana" in reason.lower()
