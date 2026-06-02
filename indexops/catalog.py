from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from indexops.config import IndexConfig
from indexops.path_signals import detect_year_from_path, infer_area_from_path, infer_client_folder
from indexops.safety import assert_read_only_target
from indexops.sqlite_store import file_sha256
from indexops.walker import iter_scan_files

CATALOG_FIELDS = [
    "ruta_absoluta",
    "ruta_relativa",
    "nombre",
    "extension",
    "tamano_bytes",
    "tamano_mb",
    "fecha_modificacion",
    "cliente_carpeta",
    "area_probable",
    "anio_probable",
    "hash_archivo",
    "error",
]


@dataclass(frozen=True)
class CatalogResult:
    output_path: Path
    total_rows: int
    counts: Counter


def write_catalog(config: IndexConfig, output_path: Path | None = None) -> CatalogResult:
    out = output_path or config.catalog_output_path
    assert_read_only_target(out, config.scan_root, config.data_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    total = 0
    limit = config.max_files_per_index_run

    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CATALOG_FIELDS)
        writer.writeheader()
        for path in iter_scan_files(config):
            if limit > 0 and total >= limit:
                counts["limite_alcanzado"] += 1
                break
            try:
                row = _row(config, path)
                estado = "ok"
            except OSError as exc:
                row = _error_row(path, str(exc))
                estado = "error"
            writer.writerow(row)
            counts[estado] += 1
            total += 1

    return CatalogResult(out, total, counts)


def _row(config: IndexConfig, path: Path) -> dict[str, str]:
    stat = path.stat()
    try:
        rel = str(path.relative_to(config.scan_root))
    except ValueError:
        rel = path.name
    file_hash = file_sha256(path) if config.index_hash_files else ""
    return {
        "ruta_absoluta": str(path.resolve()),
        "ruta_relativa": rel,
        "nombre": path.name,
        "extension": path.suffix.lower(),
        "tamano_bytes": str(stat.st_size),
        "tamano_mb": f"{stat.st_size / (1024 * 1024):.2f}",
        "fecha_modificacion": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "cliente_carpeta": infer_client_folder(path, config.scan_root, config.special_roots),
        "area_probable": infer_area_from_path(path),
        "anio_probable": detect_year_from_path(path),
        "hash_archivo": file_hash,
        "error": "",
    }


def _error_row(path: Path, error: str) -> dict[str, str]:
    return {field: "" for field in CATALOG_FIELDS} | {
        "ruta_absoluta": str(path),
        "nombre": path.name,
        "error": error,
    }
