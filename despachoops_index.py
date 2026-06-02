#!/usr/bin/env python3
"""CLI DespachoOps Index — indexación de solo lectura."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from indexops.config import load_config
from indexops.indexer import build_index, search_index
from indexops.night_runner import run_night_cycle, run_worker_loop
from indexops.catalog import write_catalog
from indexops.ocr_worker import run_ocr_worker
from indexops.safety import verify_scan_root_access
from indexops.night_window import can_run_now
from indexops.idle import user_idle_minutes
from indexops.ocr import tesseract_available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DespachoOps Index — indexa la base de clientes sin mover archivos.",
    )
    parser.add_argument("--config", default="config.yaml", help="Ruta al YAML de configuración")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Comprueba rutas, ventana y dependencias OCR")

    p_init = sub.add_parser("init", help="Crea data_dir y copia config de ejemplo si falta")
    p_init.add_argument("--force", action="store_true")

    p_index = sub.add_parser("index", help="Actualiza índice SQLite (solo lectura en scan_root)")
    p_index.add_argument("--rebuild", action="store_true")
    p_index.add_argument("--force", action="store_true", help="Ignora ventana e inactividad")

    sub.add_parser("catalog", help="Exporta CSV de inventario (solo lectura)")

    p_search = sub.add_parser("search", help="Busca en el índice")
    p_search.add_argument("query")
    p_search.add_argument("--client", default="")
    p_search.add_argument("--limit", type=int, default=20)

    p_ocr = sub.add_parser("ocr-worker", help="Procesa cola OCR nocturna")
    p_ocr.add_argument("--force", action="store_true")

    p_night = sub.add_parser("night-cycle", help="Catálogo + índice + OCR en ventana 23:00–06:00")
    p_night.add_argument("--skip-catalog", action="store_true")
    p_night.add_argument("--rebuild", action="store_true")
    p_night.add_argument("--force", action="store_true")

    p_worker = sub.add_parser("worker", help="Bucle cada N minutos (solo actúa en ventana)")
    p_worker.add_argument("--once", action="store_true")
    p_worker.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if args.command == "init":
        return cmd_init(config_path, force=args.force)
    if not config_path.exists():
        print(f"No existe config: {config_path}. Ejecuta: python despachoops_index.py init", file=sys.stderr)
        return 2
    config = load_config(config_path)

    if args.command == "doctor":
        return cmd_doctor(config)
    if args.command == "index":
        if not args.force:
            ok, reason = _guard(config)
            if not ok:
                print(reason)
                return 0
        result = build_index(config, rebuild=args.rebuild)
        print(
            f"Índice {result.db_path}: escaneados={result.scanned} nuevos={result.inserted} "
            f"actualizados={result.updated} sin_cambio={result.skipped} textos={result.text_indexed}"
        )
        return 0
    if args.command == "catalog":
        result = write_catalog(config)
        print(f"Catálogo {result.output_path}: {result.total_rows} filas")
        return 0
    if args.command == "search":
        rows = search_index(config, args.query, client_filter=args.client, limit=args.limit)
        for row in rows:
            print(f"{row['cliente']}\t{row['nombre']}\t{row['ruta']}")
        print(f"--- {len(rows)} resultados")
        return 0
    if args.command == "ocr-worker":
        if not getattr(args, "force", False):
            ok, reason = _guard(config)
            if not ok:
                print(reason)
                return 0
        result = run_ocr_worker(config)
        print(f"OCR: procesados={result.processed} descubiertos={result.discovered} locked={result.locked}")
        return 0
    if args.command == "night-cycle":
        result = run_night_cycle(
            config,
            skip_catalog=args.skip_catalog,
            rebuild_index=args.rebuild,
            force=args.force,
        )
        if not result.ok:
            print(result.reason)
            return 0 if not args.force else 1
        print(
            f"Ciclo OK: index={result.index_scanned} OCR proc={result.ocr_processed} "
            f"disc={result.ocr_discovered}"
        )
        return 0
    if args.command == "worker":
        run_worker_loop(config, once=args.once, force=args.force)
        return 0
    return 1


def _guard(config) -> tuple[bool, str]:
    idle = user_idle_minutes(config.require_idle_minutes)
    return can_run_now(config, idle_ok=idle)


def cmd_init(config_path: Path, *, force: bool) -> int:
    example = Path(__file__).parent / "config.yaml"
    if config_path.exists() and not force:
        print(f"Ya existe {config_path}")
    else:
        config_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Creado {config_path}")
    from indexops.config import load_config

    cfg = load_config(config_path)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    cfg.ocr_cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"data_dir listo: {cfg.data_dir}")
    return 0


def cmd_doctor(config) -> int:
    print(f"config: {config.config_source}")
    print(f"scan_root: {config.scan_root}")
    ok, msg = verify_scan_root_access(config.scan_root)
    print(f"  acceso: {'OK' if ok else 'FALLO'} — {msg}")
    print(f"data_dir: {config.data_dir} (escritura local)")
    print(f"index_db: {config.index_db_path}")
    print(f"ventana: {config.night_window_start} – {config.night_window_end}")
    idle = user_idle_minutes(config.require_idle_minutes)
    allowed, reason = can_run_now(config, idle_ok=idle)
    print(f"ahora ejecutaría ciclo: {allowed} ({reason})")
    print(f"Tesseract: {'sí' if tesseract_available() else 'no (OCR limitado)'}")
    print(f"OCR worker: {'activado' if config.ocr_worker_enabled else 'desactivado'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
