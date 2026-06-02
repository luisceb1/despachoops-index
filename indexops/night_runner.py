from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from indexops.catalog import write_catalog
from indexops.config import IndexConfig
from indexops.idle import user_idle_minutes
from indexops.indexer import build_index
from indexops.night_window import can_run_now
from indexops.llm_enrichment import run_llm_enrichment
from indexops.ocr_worker import run_ocr_worker
from indexops.safety import assert_read_only_target, verify_scan_root_access


@dataclass(frozen=True)
class NightCycleResult:
    ok: bool
    reason: str
    index_scanned: int = 0
    index_inserted: int = 0
    index_updated: int = 0
    ocr_processed: int = 0
    ocr_discovered: int = 0
    llm_processed: int = 0
    llm_enriched: int = 0


def setup_logging(config: IndexConfig) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.log_dir / "despachoops_index.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def run_night_cycle(
    config: IndexConfig,
    *,
    skip_catalog: bool = False,
    rebuild_index: bool = False,
    force: bool = False,
) -> NightCycleResult:
    setup_logging(config)
    log = logging.getLogger("night")

    accessible, msg = verify_scan_root_access(config.scan_root)
    if not accessible:
        log.error("scan_root: %s", msg)
        return NightCycleResult(False, msg)

    idle_ok = user_idle_minutes(config.require_idle_minutes) if not force else True
    allowed, reason = can_run_now(config, idle_ok=idle_ok)
    if not allowed and not force:
        log.info("Ciclo omitido: %s", reason)
        return NightCycleResult(False, reason)

    log.info("Iniciando ciclo nocturno sobre %s", config.scan_root)

    run_catalog = not skip_catalog and config.catalog_each_night_cycle
    if run_catalog:
        cat = write_catalog(config)
        log.info("Catálogo: %s filas (%s)", cat.total_rows, dict(cat.counts))
    elif not skip_catalog:
        log.info("Catálogo omitido (catalog_each_night_cycle=false; evita barrido SMB)")

    with _worker_lock(config):
        idx = build_index(config, rebuild=rebuild_index)
        log.info(
            "Índice: escaneados=%s nuevos=%s actualizados=%s omitidos=%s textos=%s",
            idx.scanned,
            idx.inserted,
            idx.updated,
            idx.skipped,
            idx.text_indexed,
        )
        ocr = run_ocr_worker(config)
        if ocr.disabled:
            log.info("OCR desactivado en config")
        elif ocr.outside_window:
            log.info("OCR fuera de ventana")
        elif ocr.locked:
            log.info("OCR: cola bloqueada por otro proceso")
        else:
            log.info("OCR: procesados=%s descubiertos=%s", ocr.processed, ocr.discovered)

        llm = run_llm_enrichment(config, force=force)
        if llm.disabled:
            log.info("LLM desactivado")
        elif llm.outside_window:
            log.info("LLM fuera de ventana")
        elif llm.preflight_failed:
            log.warning("LLM preflight: %s", llm.preflight_failed)
        else:
            log.info(
                "LLM: proc=%s ok=%s omitidos=%s errores=%s",
                llm.processed,
                llm.enriched,
                llm.skipped,
                llm.errors,
            )

    return NightCycleResult(
        True,
        "OK",
        index_scanned=idx.scanned,
        index_inserted=idx.inserted,
        index_updated=idx.updated,
        ocr_processed=ocr.processed if config.ocr_worker_enabled else 0,
        ocr_discovered=ocr.discovered if config.ocr_worker_enabled else 0,
        llm_processed=llm.processed if config.llm.enabled else 0,
        llm_enriched=llm.enriched if config.llm.enabled else 0,
    )


def run_worker_loop(config: IndexConfig, *, once: bool = False, force: bool = False) -> None:
    setup_logging(config)
    log = logging.getLogger("worker")
    while True:
        result = run_night_cycle(config, force=force)
        if once:
            return
        if not config.worker_enabled:
            log.info("Worker desactivado")
            return
        log.info("Esperando %s s", config.worker_interval_seconds)
        time.sleep(config.worker_interval_seconds)


@contextmanager
def _worker_lock(config: IndexConfig):
    path = config.worker_lock_path
    assert_read_only_target(path, config.scan_root, config.data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age_min = (time.time() - path.stat().st_mtime) / 60
        if age_min > config.worker_stale_lock_minutes:
            path.unlink(missing_ok=True)
        else:
            raise FileExistsError(f"Lock activo: {path}")
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
