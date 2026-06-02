from __future__ import annotations

import csv
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from indexops.config import IndexConfig
from indexops.ocr import extract_pdf_text_with_ocr, extract_text_with_ocr
from indexops.safety import assert_read_only_target, is_path_under_scan
from indexops.sqlite_store import file_sha256
from indexops.walker import iter_scan_files

OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
OCR_QUEUE_FIELDS = [
    "ruta",
    "hash_archivo",
    "extension",
    "tamano_bytes",
    "estado",
    "intentos",
    "ultimo_status",
    "cache_path",
    "actualizado",
]


@dataclass(frozen=True)
class OcrWorkerResult:
    processed: int
    discovered: int
    outside_window: bool
    disabled: bool
    locked: bool
    queue_path: Path


def run_ocr_worker(config: IndexConfig, now: datetime | None = None) -> OcrWorkerResult:
    if not config.ocr_worker_enabled:
        return OcrWorkerResult(0, 0, False, True, False, config.ocr_queue_path)

    from indexops.night_window import inside_night_window

    current = now or datetime.now()
    if not inside_night_window(
        current.time(),
        config.night_window_start,
        config.night_window_end,
    ):
        return OcrWorkerResult(0, 0, True, False, False, config.ocr_queue_path)

    lock = config.ocr_queue_path.with_suffix(".lock")
    try:
        with _lock(lock, config):
            rows = _read_queue(config.ocr_queue_path)
            discovered = _discover(config, rows, current)
            processed = _process(config, rows, current)
            _write_queue(config.ocr_queue_path, config, rows)
            return OcrWorkerResult(
                processed,
                discovered,
                False,
                False,
                False,
                config.ocr_queue_path,
            )
    except FileExistsError:
        return OcrWorkerResult(0, 0, False, False, True, config.ocr_queue_path)


def _discover(config: IndexConfig, rows: list[dict[str, str]], current: datetime) -> int:
    known = {r.get("ruta", "") for r in rows}
    found = 0
    for path in iter_scan_files(config):
        if path.suffix.lower() not in OCR_EXTENSIONS:
            continue
        rendered = str(path)
        if rendered in known:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        rows.append(
            {
                "ruta": rendered,
                "hash_archivo": "",
                "extension": path.suffix.lower(),
                "tamano_bytes": str(size),
                "estado": "pendiente",
                "intentos": "0",
                "ultimo_status": "",
                "cache_path": "",
                "actualizado": current.isoformat(timespec="seconds"),
            }
        )
        known.add(rendered)
        found += 1
        if config.max_files_per_ocr_run > 0 and found >= config.max_files_per_ocr_run * 2:
            break
    return found


def _process(config: IndexConfig, rows: list[dict[str, str]], current: datetime) -> int:
    config.ocr_cache_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for row in rows:
        if config.max_files_per_ocr_run > 0 and processed >= config.max_files_per_ocr_run:
            break
        if row.get("estado") not in {"pendiente", "error"}:
            continue
        path = Path(row.get("ruta", ""))
        if not path.is_file() or not is_path_under_scan(path, config.scan_root):
            _set_row(row, "no_encontrado", "", "", current)
            continue
        if _too_large(path, config.ocr_skip_large_files_mb):
            _set_row(row, "omitido_tamano", "", "", current)
            continue

        file_hash = row.get("hash_archivo") or file_sha256(path)
        cache_path = config.ocr_cache_dir / f"{file_hash}.txt"
        assert_read_only_target(cache_path, config.scan_root, config.data_dir)
        row["hash_archivo"] = file_hash

        if cache_path.exists():
            _set_row(row, "ocr_cache", "CACHE_OK", str(cache_path), current)
            processed += 1
            continue

        row["intentos"] = str(int(row.get("intentos") or "0") + 1)
        if path.suffix.lower() == ".pdf":
            result = extract_pdf_text_with_ocr(
                path,
                max_pages=config.ocr_max_pages_per_file,
                languages=config.ocr_languages,
            )
        else:
            result = extract_text_with_ocr(path, languages=config.ocr_languages)

        if result.text:
            cache_path.write_text(result.text, encoding="utf-8")
            _set_row(row, "ocr_ok", result.status, str(cache_path), current)
        elif "NO_DISPONIBLE" in result.status:
            _set_row(row, "ocr_no_disponible", result.status, "", current)
        else:
            _set_row(row, "sin_texto", result.status, "", current)
        processed += 1
    return processed


def _set_row(row: dict[str, str], state: str, status: str, cache: str, current: datetime) -> None:
    row["estado"] = state
    row["ultimo_status"] = status
    row["cache_path"] = cache
    row["actualizado"] = current.isoformat(timespec="seconds")


def _too_large(path: Path, max_mb: int) -> bool:
    return max_mb > 0 and path.stat().st_size > max_mb * 1024 * 1024


def _read_queue(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_queue(path: Path, config: IndexConfig, rows: list[dict[str, str]]) -> None:
    assert_read_only_target(path, config.scan_root, config.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OCR_QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


@contextmanager
def _lock(path: Path, config: IndexConfig):
    assert_read_only_target(path, config.scan_root, config.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("x", encoding="utf-8")
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
