from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from despachoops_index.config import AppConfig
from despachoops_index.idle import user_idle_minutes
from despachoops_index.indexer import build_index
from despachoops_index.llm_enrichment import run_llm_enrichment
from despachoops_index.night_window import can_run_now
from despachoops_index.ocr_worker import run_ocr_worker
from despachoops_index.safety import assert_writable_data_path, verify_scan_root


@dataclass(frozen=True)
class NightCycleResult:
    ok: bool
    reason: str
    indexed: int = 0
    skipped_unchanged: int = 0
    ocr_processed: int = 0
    llm_enriched: int = 0


def setup_logging(config: AppConfig) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(config.log_dir / "despachoops_index.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def run_night_cycle(config: AppConfig, *, force: bool = False) -> NightCycleResult:
    setup_logging(config)
    log = logging.getLogger("night")
    ok_root, msg = verify_scan_root(config.scan_root)
    if not ok_root:
        log.error(msg)
        return NightCycleResult(False, msg)
    idle = user_idle_minutes(config.require_idle_minutes) if not force else True
    allowed, reason = can_run_now(config, idle_ok=idle)
    if not allowed and not force:
        log.info("Omitido: %s", reason)
        return NightCycleResult(False, reason)

    log.info("Ciclo nocturno en %s", config.scan_root)
    if config.catalog_each_night_cycle:
        log.warning("catalog_each_night_cycle=true implica barrido SMB completo")

    with _worker_lock(config):
        idx = build_index(config.to_index_options())
        log.info(
            "Índice: +%s sin_cambio=%s textos=%s",
            idx.indexed,
            idx.skipped_unchanged,
            idx.with_text,
        )
        ocr = run_ocr_worker(config)
        log.info("OCR: proc=%s desc=%s", ocr.processed, ocr.discovered)
        llm = run_llm_enrichment(config, force=force)
        if llm.preflight_failed:
            log.warning("LLM: %s", llm.preflight_failed)
        else:
            log.info("LLM: ok=%s proc=%s", llm.enriched, llm.processed)

    return NightCycleResult(
        True,
        "OK",
        indexed=idx.indexed,
        skipped_unchanged=idx.skipped_unchanged,
        ocr_processed=ocr.processed,
        llm_enriched=llm.enriched,
    )


def run_worker_loop(config: AppConfig, *, once: bool = False, force: bool = False) -> None:
    setup_logging(config)
    log = logging.getLogger("worker")
    while True:
        run_night_cycle(config, force=force)
        if once or not config.worker_enabled:
            return
        log.info("Espera %ss", config.worker_interval_seconds)
        time.sleep(config.worker_interval_seconds)


@contextmanager
def _worker_lock(config: AppConfig):
    path = config.worker_lock_path
    assert_writable_data_path(path, config.scan_root, config.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = (time.time() - path.stat().st_mtime) / 60
        if age > config.worker_stale_lock_minutes:
            path.unlink(missing_ok=True)
        else:
            raise FileExistsError(f"Lock activo: {path}")
    handle = path.open("x", encoding="utf-8")
    try:
        handle.write(str(os.getpid()))
        handle.close()
        yield
    finally:
        path.unlink(missing_ok=True)
