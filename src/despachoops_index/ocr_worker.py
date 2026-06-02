from __future__ import annotations

import csv
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from despachoops_index.config import AppConfig
from despachoops_index.hashutil import file_sha256
from despachoops_index.night_window import inside_window
from despachoops_index.ocr import extract_pdf_text_with_ocr, extract_text_with_ocr
from despachoops_index.safety import assert_writable_data_path, is_under_scan
from despachoops_index.walk import iter_scan_files

OCR_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
QUEUE_FIELDS = [
    "ruta", "hash_archivo", "extension", "tamano_bytes",
    "estado", "intentos", "ultimo_status", "cache_path", "actualizado",
]


@dataclass(frozen=True)
class OcrWorkerResult:
    processed: int
    discovered: int
    outside_window: bool
    disabled: bool
    locked: bool


def run_ocr_worker(config: AppConfig, now: datetime | None = None) -> OcrWorkerResult:
    if not config.ocr_worker_enabled:
        return OcrWorkerResult(0, 0, False, True, False)
    current = now or datetime.now()
    if not inside_window(current.time(), config.night_window_start, config.night_window_end):
        return OcrWorkerResult(0, 0, True, False, False)
    lock = config.ocr_queue_path.with_suffix(".lock")
    try:
        with _lock(lock, config):
            rows = _read_queue(config.ocr_queue_path)
            discovered = _discover(config, rows, current)
            processed = _process(config, rows, current)
            _write_queue(config, rows)
            return OcrWorkerResult(processed, discovered, False, False, False)
    except FileExistsError:
        return OcrWorkerResult(0, 0, False, False, True)


def _discover(config: AppConfig, rows: list[dict[str, str]], now: datetime) -> int:
    known = {r.get("ruta", "") for r in rows}
    found = 0
    for path in iter_scan_files(config):
        if path.suffix.lower() not in OCR_EXT:
            continue
        key = str(path.resolve())
        if key in known:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        rows.append({
            "ruta": key, "hash_archivo": "", "extension": path.suffix.lower(),
            "tamano_bytes": str(size), "estado": "pendiente", "intentos": "0",
            "ultimo_status": "", "cache_path": "", "actualizado": now.isoformat(timespec="seconds"),
        })
        known.add(key)
        found += 1
        if config.max_files_per_ocr_run > 0 and found >= config.max_files_per_ocr_run * 2:
            break
    return found


def _process(config: AppConfig, rows: list[dict[str, str]], now: datetime) -> int:
    config.ocr_cache_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for row in rows:
        if config.max_files_per_ocr_run > 0 and processed >= config.max_files_per_ocr_run:
            break
        if row.get("estado") not in {"pendiente", "error"}:
            continue
        path = Path(row.get("ruta", ""))
        if not path.is_file() or not is_under_scan(path, config.scan_root):
            _set(row, "no_encontrado", "", "", now)
            continue
        if config.ocr_skip_large_files_mb > 0 and path.stat().st_size > config.ocr_skip_large_files_mb * 1024 * 1024:
            _set(row, "omitido_tamano", "", "", now)
            continue
        digest = row.get("hash_archivo") or file_sha256(path)
        cache = config.ocr_cache_dir / f"{digest}.txt"
        assert_writable_data_path(cache, config.scan_root, config.data_dir)
        row["hash_archivo"] = digest
        if cache.exists():
            _set(row, "ocr_cache", "CACHE_OK", str(cache), now)
            processed += 1
            continue
        row["intentos"] = str(int(row.get("intentos") or "0") + 1)
        if path.suffix.lower() == ".pdf":
            res = extract_pdf_text_with_ocr(path, config.ocr_max_pages_per_file, config.ocr_languages)
        else:
            res = extract_text_with_ocr(path, config.ocr_languages)
        if res.text:
            cache.write_text(res.text, encoding="utf-8")
            _set(row, "ocr_ok", res.status, str(cache), now)
        else:
            _set(row, "sin_texto" if "SIN_TEXTO" in res.status else "error", res.status, "", now)
        processed += 1
    return processed


def _set(row: dict, state: str, status: str, cache: str, now: datetime) -> None:
    row.update({
        "estado": state, "ultimo_status": status, "cache_path": cache,
        "actualizado": now.isoformat(timespec="seconds"),
    })


def _read_queue(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_queue(config: AppConfig, rows: list[dict[str, str]]) -> None:
    assert_writable_data_path(config.ocr_queue_path, config.scan_root, config.data_dir)
    config.ocr_queue_path.parent.mkdir(parents=True, exist_ok=True)
    with config.ocr_queue_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        w.writeheader()
        w.writerows(rows)


@contextmanager
def _lock(path: Path, config: AppConfig):
    assert_writable_data_path(path, config.scan_root, config.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    h = path.open("x", encoding="utf-8")
    try:
        h.write(str(os.getpid()))
        h.close()
        yield
    finally:
        path.unlink(missing_ok=True)
