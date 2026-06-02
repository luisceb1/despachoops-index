from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IndexConfig:
    scan_root: Path
    data_dir: Path
    index_db_path: Path
    catalog_output_path: Path
    log_dir: Path
    ocr_cache_dir: Path
    ocr_queue_path: Path
    worker_lock_path: Path
    recursive: bool
    max_files_per_index_run: int
    max_files_per_ocr_run: int
    index_skip_large_files_mb: int
    ocr_skip_large_files_mb: int
    index_text_enabled: bool
    index_text_max_chars: int
    index_hash_files: bool
    ocr_worker_enabled: bool
    ocr_max_pages_per_file: int
    ocr_languages: str
    night_window_start: str
    night_window_end: str
    require_idle_minutes: int
    exclude_dirs: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    special_roots: tuple[str, ...]
    exclude_path_patterns: tuple[str, ...]
    worker_enabled: bool
    worker_interval_seconds: int
    worker_stale_lock_minutes: int
    config_source: Path | None = None


def load_config(path: Path | str = "config.yaml") -> IndexConfig:
    source = Path(path).resolve()
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    data_dir = Path(str(raw.get("data_dir") or "data")).expanduser()
    if not raw.get("index_db_path"):
        index_db = data_dir / "despachoops_index.sqlite"
    else:
        index_db = Path(str(raw["index_db_path"]))
    catalog = Path(str(raw["catalog_output_path"])) if raw.get("catalog_output_path") else data_dir / "catalogo_clientes.csv"
    log_dir = Path(str(raw["log_dir"])) if raw.get("log_dir") else data_dir / "logs"
    ocr_cache = Path(str(raw["ocr_cache_dir"])) if raw.get("ocr_cache_dir") else data_dir / "ocr_cache"
    ocr_queue = Path(str(raw["ocr_queue_path"])) if raw.get("ocr_queue_path") else data_dir / "ocr_jobs.csv"
    lock_path = Path(str(raw["worker_lock_path"])) if raw.get("worker_lock_path") else data_dir / ".despachoops_index.lock"
    worker = raw.get("worker") or {}
    return IndexConfig(
        scan_root=Path(str(raw.get("scan_root") or ".")).expanduser(),
        data_dir=data_dir,
        index_db_path=index_db,
        catalog_output_path=catalog,
        log_dir=log_dir,
        ocr_cache_dir=ocr_cache,
        ocr_queue_path=ocr_queue,
        worker_lock_path=lock_path,
        recursive=bool(raw.get("recursive", True)),
        max_files_per_index_run=int(raw.get("max_files_per_index_run", 5000)),
        max_files_per_ocr_run=int(raw.get("max_files_per_ocr_run", 150)),
        index_skip_large_files_mb=int(raw.get("index_skip_large_files_mb", 80)),
        ocr_skip_large_files_mb=int(raw.get("ocr_skip_large_files_mb", 120)),
        index_text_enabled=bool(raw.get("index_text_enabled", True)),
        index_text_max_chars=int(raw.get("index_text_max_chars", 20000)),
        index_hash_files=bool(raw.get("index_hash_files", False)),
        ocr_worker_enabled=bool(raw.get("ocr_worker_enabled", True)),
        ocr_max_pages_per_file=int(raw.get("ocr_max_pages_per_file", 15)),
        ocr_languages=str(raw.get("ocr_languages", "spa+eng")),
        night_window_start=str(raw.get("night_window_start", "23:00")),
        night_window_end=str(raw.get("night_window_end", "06:00")),
        require_idle_minutes=int(raw.get("require_idle_minutes", 10)),
        exclude_dirs=_tuple(raw.get("exclude_dirs")),
        exclude_patterns=_tuple(raw.get("exclude_patterns")),
        special_roots=_tuple(raw.get("special_roots")),
        exclude_path_patterns=_tuple(raw.get("exclude_path_patterns")),
        worker_enabled=bool(worker.get("enabled", True)),
        worker_interval_seconds=int(worker.get("interval_seconds", 600)),
        worker_stale_lock_minutes=int(worker.get("stale_lock_minutes", 180)),
        config_source=source,
    )


def _tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(item) for item in value)
