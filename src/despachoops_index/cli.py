from __future__ import annotations

import argparse
import sys
from pathlib import Path

from despachoops_index.config import IndexOptions, load_app_config, resolve_paths
from despachoops_index.dashboard import build_dashboard
from despachoops_index.indexer import build_index
from despachoops_index.llm_enrichment import count_llm_pending, run_llm_enrichment
from despachoops_index.llm.ollama_client import OllamaClient, profile_to_client
from despachoops_index.night_runner import run_night_cycle, run_worker_loop
from despachoops_index.night_window import can_run_now
from despachoops_index.ocr import tesseract_available
from despachoops_index.ocr_worker import run_ocr_worker
from despachoops_index.search import search
from despachoops_index.idle import user_idle_minutes
from despachoops_index.safety import assert_writable_output_path, verify_scan_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DespachoOps Index — solo lectura.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="config.yaml (producción / nocturno). Usar antes del subcomando.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Comprueba red, ventana, OCR y Ollama")
    p_init = sub.add_parser("init", help="Crea data_dir local")
    p_init.add_argument("--force", action="store_true")

    p_index = sub.add_parser("index", help="Indexa carpeta raíz")
    p_index.add_argument("--root", default="")
    p_index.add_argument("--db", default="")
    p_index.add_argument("--limit", type=int, default=0)
    p_index.add_argument("--text", action="store_true")
    p_index.add_argument("--force", action="store_true")

    p_search = sub.add_parser("search", help="Buscar en índice")
    p_search.add_argument("query")
    p_search.add_argument("--db", default="")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--ext", default="")

    p_dash = sub.add_parser("dashboard", help="Excel de diagnóstico")
    p_dash.add_argument("--db", default="")
    p_dash.add_argument(
        "--output",
        default="",
        help="Ruta .xlsx (opcional; por defecto reports_dir/index_dashboard_YYYYMMDD_HHMMSS.xlsx)",
    )

    p_ocr = sub.add_parser("ocr-worker", help="Cola OCR nocturna")
    p_ocr.add_argument("--force", action="store_true")

    p_llm = sub.add_parser("llm-enrich", help="Enriquecimiento Ollama (texto local)")
    p_llm.add_argument("--force", action="store_true")

    p_night = sub.add_parser("night-cycle", help="Índice + OCR + LLM (23:00–06:00)")
    p_night.add_argument("--force", action="store_true")

    p_worker = sub.add_parser("worker", help="Bucle nocturno")
    p_worker.add_argument("--once", action="store_true")
    p_worker.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    config_path = Path(args.config).expanduser()

    if args.command == "init":
        return _cmd_init(config_path, force=args.force)

    if args.command in {"doctor", "ocr-worker", "llm-enrich", "night-cycle", "worker"}:
        if not config_path.exists():
            print(f"Falta {config_path}", file=sys.stderr)
            return 2
        app = load_app_config(config_path)
        return _run_app_command(args, app)

    if args.command == "index":
        if config_path.exists() and not args.root:
            app = load_app_config(config_path)
            opts = app.to_index_options(include_text=args.text, limit=args.limit or None)
            if args.force:
                opts = IndexOptions(
                    root=opts.root, db_path=opts.db_path, limit=opts.limit,
                    include_text=opts.include_text, incremental=False,
                    use_ocr_cache=opts.use_ocr_cache, ocr_cache_dir=opts.ocr_cache_dir,
                    skip_large_files_mb=opts.skip_large_files_mb,
                    exclude_dirs=opts.exclude_dirs,
                    exclude_patterns=opts.exclude_patterns,
                    exclude_path_patterns=opts.exclude_path_patterns,
                    exclude_extensions=opts.exclude_extensions,
                )
        elif args.root and args.db:
            opts = resolve_paths(args.root, args.db)
            opts = IndexOptions(
                root=opts.root, db_path=opts.db_path,
                limit=max(0, args.limit), include_text=args.text,
            )
        else:
            print("index requiere --root y --db, o --config", file=sys.stderr)
            return 2
        try:
            result = build_index(opts)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(
            f"Índice {result.db_path}: +{result.indexed} escaneados={result.scanned} "
            f"sin_cambio={result.skipped_unchanged} ignorados={result.skipped_ignored} "
            f"textos={result.with_text} fts={result.fts_enabled}"
        )
        return 0

    db_path = _resolve_db(args, config_path)
    if not db_path.exists():
        print(f"No existe DB: {db_path}", file=sys.stderr)
        return 2

    if args.command == "search":
        for hit in search(db_path, args.query, limit=args.limit, extension=args.ext):
            print(f"{hit.score}\t{hit.extension}\t{hit.name}\t{hit.path}")
        return 0

    if args.command == "dashboard":
        return _cmd_dashboard(args, config_path, db_path)

    return 1


def _resolve_db(args, config_path: Path) -> Path:
    if getattr(args, "db", "") and args.db:
        return Path(args.db).expanduser().resolve()
    if config_path.exists():
        return load_app_config(config_path).index_db_path
    return Path("data/despacho_index.sqlite")


def _cmd_init(config_path: Path, *, force: bool) -> int:
    if not config_path.exists():
        print(f"No existe {config_path}", file=sys.stderr)
        return 2
    app = load_app_config(config_path)
    for d in (app.data_dir, app.log_dir, app.ocr_cache_dir, app.reports_dir):
        assert_writable_output_path(d, app.scan_root, app.writable_output_roots())
        d.mkdir(parents=True, exist_ok=True)
    assert_writable_output_path(app.index_db_path, app.scan_root, (app.data_dir,))
    app.index_db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"data_dir: {app.data_dir}")
    print(f"reports_dir: {app.reports_dir}")
    return 0


def _cmd_dashboard(args, config_path: Path, db_path: Path) -> int:
    if not db_path.exists():
        print(f"No existe DB: {db_path}", file=sys.stderr)
        return 2

    app = load_app_config(config_path) if config_path.exists() else None

    if args.output:
        out = Path(args.output).expanduser()
    elif app is not None:
        out = app.default_dashboard_path()
    else:
        print(
            "dashboard sin --output requiere --config con reports_dir",
            file=sys.stderr,
        )
        return 2

    if app is not None and not args.db:
        assert_writable_output_path(out, app.scan_root, app.writable_output_roots())
    else:
        data_root = db_path.parent
        assert_writable_output_path(
            out, data_root, (data_root,), check_scan=False
        )

    try:
        out = out.resolve()
    except OSError:
        out = out.absolute()
    r = build_dashboard(db_path, out)
    print(f"Dashboard: {r.output_path}")
    return 0


def _run_app_command(args, app) -> int:
    if args.command == "doctor":
        print(f"scan_root: {app.scan_root}")
        ok, msg = verify_scan_root(app.scan_root)
        print(f"  acceso: {'OK' if ok else msg}")
        print(f"data_dir: {app.data_dir}")
        print(f"reports_dir: {app.reports_dir}")
        print(f"ventana: {app.night_window_start}-{app.night_window_end}")
        idle = user_idle_minutes(app.require_idle_minutes)
        allowed, reason = can_run_now(app, idle_ok=idle)
        print(f"ciclo ahora: {allowed} ({reason})")
        print(f"Tesseract: {'sí' if tesseract_available() else 'no'}")
        if app.llm.enabled:
            c = OllamaClient(profile_to_client(app.llm.profile))
            llm_ok, llm_msg = c.preflight()
            print(f"Ollama: {'OK' if llm_ok else llm_msg}; pendientes={count_llm_pending(app)}")
        return 0 if ok else 1

    if args.command == "ocr-worker":
        if not args.force:
            ok, reason = can_run_now(app, idle_ok=user_idle_minutes(app.require_idle_minutes))
            if not ok:
                print(reason)
                return 0
        r = run_ocr_worker(app)
        print(f"OCR proc={r.processed} desc={r.discovered} locked={r.locked}")
        return 0

    if args.command == "llm-enrich":
        if not args.force:
            ok, reason = can_run_now(app, idle_ok=user_idle_minutes(app.require_idle_minutes))
            if not ok:
                print(reason)
                return 0
        r = run_llm_enrichment(app, force=args.force)
        if r.preflight_failed:
            print(r.preflight_failed, file=sys.stderr)
            return 1
        print(f"LLM ok={r.enriched} proc={r.processed} err={r.errors}")
        return 0

    if args.command == "night-cycle":
        r = run_night_cycle(app, force=args.force)
        if not r.ok:
            print(r.reason)
            return 0
        print(f"OK index+{r.indexed} ocr={r.ocr_processed} llm={r.llm_enriched}")
        return 0

    if args.command == "worker":
        run_worker_loop(app, once=args.once, force=args.force)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
