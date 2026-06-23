from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from despachoops_index.config import LONG_PATH_THRESHOLD, DOCUMENT_EXTENSIONS


@dataclass(frozen=True)
class DashboardResult:
    output_path: Path
    sheets: tuple[str, ...]


def build_dashboard(db_path: Path, output_path: Path) -> DashboardResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        summary = _summary(conn)
        by_ext = _by_extension(conn)
        long_paths = _long_paths(conn)
        sin_texto = _sin_texto(conn)
        pdfs = _pdfs(conn)
        duplicates = _duplicates(conn)
        ignored = _ignored(conn)

        wb = Workbook()
        wb.remove(wb.active)
        _write_sheet(wb, "Resumen", ["metrica", "valor"], summary)
        _write_sheet(wb, "Extensiones", ["extension", "archivos"], by_ext)
        _write_sheet(wb, "Rutas_Largas", ["path", "path_length", "name"], long_paths)
        _write_sheet(
            wb,
            "Sin_Texto",
            ["path", "extension", "read_error", "size_bytes", "name"],
            sin_texto,
        )
        _write_sheet(wb, "PDFs", ["path", "size_bytes", "mtime_iso", "read_error"], pdfs)
        _write_sheet(
            wb,
            "Duplicados_Probables",
            ["name", "size_bytes", "copias", "paths"],
            duplicates,
        )
        _write_sheet(wb, "Archivos_Temporales_Ignorados", ["path", "name", "reason"], ignored)
        wb.save(output_path)
        return DashboardResult(
            output_path,
            (
                "Resumen",
                "Extensiones",
                "Rutas_Largas",
                "Sin_Texto",
                "PDFs",
                "Duplicados_Probables",
                "Archivos_Temporales_Ignorados",
            ),
        )
    finally:
        conn.close()


def _summary(conn: sqlite3.Connection) -> list[dict[str, str]]:
    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    with_text = conn.execute(
        """
        SELECT COUNT(*) FROM files f
        JOIN file_text t ON t.file_id = f.id
        WHERE COALESCE(t.text_preview, '') != '' AND COALESCE(f.read_error, '') = ''
        """
    ).fetchone()[0]
    errors = conn.execute(
        "SELECT COUNT(*) FROM files WHERE read_error IS NOT NULL AND read_error != ''"
    ).fetchone()[0]
    long_count = conn.execute(
        "SELECT COUNT(*) FROM files WHERE path_length >= ?", (LONG_PATH_THRESHOLD,)
    ).fetchone()[0]
    ignored = conn.execute("SELECT COUNT(*) FROM ignored_files").fetchone()[0]
    dup_groups = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT name, size_bytes FROM files
            GROUP BY name, size_bytes HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    return [
        {"metrica": "total_indexados", "valor": str(total)},
        {"metrica": "con_texto", "valor": str(with_text)},
        {"metrica": "read_error", "valor": str(errors)},
        {"metrica": "rutas_largas", "valor": str(long_count)},
        {"metrica": "grupos_duplicados_probables", "valor": str(dup_groups)},
        {"metrica": "archivos_ignorados", "valor": str(ignored)},
        {"metrica": "umbral_ruta_larga", "valor": str(LONG_PATH_THRESHOLD)},
    ]


def _by_extension(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(extension, ''), '(sin)') AS ext, COUNT(*) AS c
        FROM files GROUP BY ext ORDER BY c DESC
        """
    ).fetchall()
    return [{"extension": r[0], "archivos": str(r[1])} for r in rows]


def _long_paths(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT path, path_length, name FROM files
        WHERE path_length >= ?
        ORDER BY path_length DESC
        LIMIT 5000
        """,
        (LONG_PATH_THRESHOLD,),
    ).fetchall()
    return [{"path": r[0], "path_length": str(r[1]), "name": r[2]} for r in rows]


def _sin_texto(conn: sqlite3.Connection) -> list[dict[str, str]]:
    placeholders = ",".join("?" for _ in DOCUMENT_EXTENSIONS)
    rows = conn.execute(
        f"""
        SELECT f.path, f.extension, COALESCE(f.read_error, '') AS read_error,
               f.size_bytes, f.name,
               COALESCE(t.text_preview, '') AS text_preview
        FROM files f
        LEFT JOIN file_text t ON t.file_id = f.id
        WHERE LOWER(f.extension) IN ({placeholders})
          AND (
            COALESCE(f.read_error, '') != ''
            OR t.file_id IS NULL
            OR TRIM(COALESCE(t.text_preview, '')) = ''
            OR LOWER(TRIM(t.text_preview)) = 'sin_texto'
            OR LOWER(TRIM(t.text_preview)) LIKE 'read_error:%'
          )
        ORDER BY f.path
        LIMIT 5000
        """,
        tuple(ext.lower() for ext in DOCUMENT_EXTENSIONS),
    ).fetchall()
    return [
        {
            "path": r[0],
            "extension": r[1],
            "read_error": r[2] or _preview_as_error(r[5]),
            "size_bytes": str(r[3] if r[3] is not None else ""),
            "name": r[4] or "",
        }
        for r in rows
    ]


def _preview_as_error(preview: str) -> str:
    p = (preview or "").strip().lower()
    if p in {"sin_texto", "read_error"} or p.startswith("read_error:"):
        return preview.strip()
    return ""


def _pdfs(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT path, size_bytes, mtime_iso, COALESCE(read_error, '') AS read_error
        FROM files WHERE extension = '.pdf'
        ORDER BY path
        LIMIT 10000
        """
    ).fetchall()
    return [
        {
            "path": r[0],
            "size_bytes": str(r[1]),
            "mtime_iso": r[2],
            "read_error": r[3],
        }
        for r in rows
    ]


def _duplicates(conn: sqlite3.Connection) -> list[dict[str, str]]:
    groups = conn.execute(
        """
        SELECT name, size_bytes, COUNT(*) AS c
        FROM files
        GROUP BY name, size_bytes
        HAVING c > 1
        ORDER BY c DESC, name
        LIMIT 2000
        """
    ).fetchall()
    result: list[dict[str, str]] = []
    for name, size, count in groups:
        paths = conn.execute(
            "SELECT path FROM files WHERE name = ? AND size_bytes = ? ORDER BY path",
            (name, size),
        ).fetchall()
        result.append(
            {
                "name": name,
                "size_bytes": str(size),
                "copias": str(count),
                "paths": " | ".join(p[0] for p in paths),
            }
        )
    return result


def _ignored(conn: sqlite3.Connection) -> list[dict[str, str]]:
    try:
        rows = conn.execute(
            "SELECT path, name, reason FROM ignored_files ORDER BY path LIMIT 5000"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"path": r[0], "name": r[1], "reason": r[2]} for r in rows]


def _write_sheet(wb: Workbook, title: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    for idx, header in enumerate(headers, start=1):
        values = [header] + [str(row.get(header, "")) for row in rows]
        width = min(60, max(10, max(len(v) for v in values) + 2))
        ws.column_dimensions[get_column_letter(idx)].width = width
