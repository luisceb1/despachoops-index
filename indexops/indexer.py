from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from indexops.config import IndexConfig
from indexops.path_signals import detect_year_from_path, infer_area_from_path, infer_client_folder
from indexops.safety import assert_read_only_target
from indexops.sqlite_store import drop_db, file_sha256, init_db
from indexops.text_reader import OCR_CACHE_EXTENSIONS, TEXT_EXTENSIONS, preview_text, read_document_text
from indexops.walker import iter_scan_files


@dataclass(frozen=True)
class IndexRunResult:
    db_path: Path
    scanned: int
    inserted: int
    updated: int
    skipped: int
    text_indexed: int
    fts_enabled: bool
    stopped_at_limit: bool


def build_index(
    config: IndexConfig,
    *,
    rebuild: bool = False,
    force_text: bool | None = None,
) -> IndexRunResult:
    assert_read_only_target(config.index_db_path, config.scan_root, config.data_dir)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    text_enabled = config.index_text_enabled if force_text is None else force_text

    conn = sqlite3.connect(config.index_db_path)
    try:
        if rebuild:
            drop_db(conn)
        fts_enabled = init_db(conn)
        scanned = inserted = updated = skipped = text_indexed = 0
        stopped = False

        for path in iter_scan_files(config):
            if config.max_files_per_index_run > 0 and scanned >= config.max_files_per_index_run:
                stopped = True
                break
            scanned += 1
            try:
                stat = path.stat()
            except OSError:
                continue

            existing = conn.execute(
                "SELECT id, size_bytes, mtime_ns FROM files WHERE path = ?",
                (str(path),),
            ).fetchone()

            if existing and existing[1] == stat.st_size and existing[2] == stat.st_mtime_ns:
                skipped += 1
                continue

            sha = file_sha256(path) if config.index_hash_files else ""
            text_source = ""
            text_full = ""
            if text_enabled and not _too_large(config, stat.st_size):
                text_source, text_full, sha = _extract_text(config, path, sha)

            cliente = infer_client_folder(path, config.scan_root, config.special_roots)
            area = infer_area_from_path(path)
            anio = detect_year_from_path(path)
            try:
                rel = str(path.relative_to(config.scan_root))
            except ValueError:
                rel = path.name
            now = datetime.now().isoformat(timespec="seconds")

            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO files (
                        path, name, extension, size_bytes, mtime_ns, sha256,
                        cliente_carpeta, area_probable, anio_probable,
                        ruta_relativa, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(path),
                        path.name,
                        path.suffix.lower(),
                        stat.st_size,
                        stat.st_mtime_ns,
                        sha,
                        cliente,
                        area,
                        anio,
                        rel,
                        now,
                    ),
                )
                file_id = int(cur.lastrowid)
                inserted += 1
            else:
                file_id = int(existing[0])
                conn.execute(
                    """
                    UPDATE files SET name=?, extension=?, size_bytes=?, mtime_ns=?, sha256=?,
                        cliente_carpeta=?, area_probable=?, anio_probable=?,
                        ruta_relativa=?, indexed_at=? WHERE id=?
                    """,
                    (
                        path.name,
                        path.suffix.lower(),
                        stat.st_size,
                        stat.st_mtime_ns,
                        sha,
                        cliente,
                        area,
                        anio,
                        rel,
                        now,
                        file_id,
                    ),
                )
                updated += 1

            if text_full:
                text_indexed += 1
            _upsert_text(conn, file_id, text_source, text_full, config.index_text_max_chars)
            _upsert_fts(
                conn,
                fts_enabled,
                file_id,
                str(path),
                path.name,
                cliente,
                area,
                text_full,
                config.index_text_max_chars,
            )

        conn.commit()
        return IndexRunResult(
            config.index_db_path,
            scanned,
            inserted,
            updated,
            skipped,
            text_indexed,
            fts_enabled,
            stopped,
        )
    finally:
        conn.close()


def search_index(
    config: IndexConfig,
    query: str,
    *,
    client_filter: str = "",
    limit: int = 30,
) -> list[dict[str, str]]:
    conn = sqlite3.connect(config.index_db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        like = f"%{query.lower()}%"
        rows = conn.execute(
            """
            SELECT f.path, f.name, f.cliente_carpeta, f.area_probable,
                   COALESCE(t.text_preview, '') AS text_preview
            FROM files f
            LEFT JOIN file_text t ON t.file_id = f.id
            WHERE LOWER(f.path) LIKE ? OR LOWER(f.name) LIKE ?
               OR LOWER(f.cliente_carpeta) LIKE ? OR LOWER(COALESCE(t.text_preview,'')) LIKE ?
            ORDER BY f.path
            LIMIT ?
            """,
            (like, like, like, like, limit * 3),
        ).fetchall()
        results = []
        for row in rows:
            if client_filter and client_filter.lower() not in str(row["cliente_carpeta"] or "").lower():
                continue
            results.append(
                {
                    "ruta": row["path"],
                    "nombre": row["name"],
                    "cliente": row["cliente_carpeta"] or "",
                    "area": row["area_probable"] or "",
                    "text_preview": row["text_preview"] or "",
                }
            )
            if len(results) >= limit:
                break
        return results
    finally:
        conn.close()


def _too_large(config: IndexConfig, size_bytes: int) -> bool:
    return config.index_skip_large_files_mb > 0 and size_bytes > config.index_skip_large_files_mb * 1024 * 1024


def _extract_text(config: IndexConfig, path: Path, sha: str) -> tuple[str, str, str]:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        doc = read_document_text(path, inline_ocr=False)
        if doc.text:
            return doc.status, doc.text[: config.index_text_max_chars], sha
    if suffix in OCR_CACHE_EXTENSIONS:
        digest = sha or file_sha256(path)
        cache = config.ocr_cache_dir / f"{digest}.txt"
        if cache.is_file():
            text = cache.read_text(encoding="utf-8", errors="ignore")
            return "OCR_CACHE", text[: config.index_text_max_chars], digest
    return "", "", sha


def _upsert_text(conn, file_id: int, source: str, full: str, max_chars: int) -> None:
    conn.execute("DELETE FROM file_text WHERE file_id = ?", (file_id,))
    conn.execute(
        "INSERT INTO file_text (file_id, text_source, text_preview, text_full) VALUES (?, ?, ?, ?)",
        (file_id, source, preview_text(full), full[:max_chars] if max_chars > 0 else ""),
    )


def _upsert_fts(
    conn,
    enabled: bool,
    file_id: int,
    path: str,
    name: str,
    cliente: str,
    area: str,
    text_full: str,
    max_chars: int,
) -> None:
    if not enabled:
        return
    conn.execute("DELETE FROM files_fts WHERE rowid = ?", (file_id,))
    conn.execute(
        """
        INSERT INTO files_fts (rowid, path, name, cliente_carpeta, area_probable, text_preview, text_full)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, path, name, cliente, area, preview_text(text_full), text_full[:max_chars]),
    )
