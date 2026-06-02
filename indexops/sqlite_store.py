from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def init_db(conn: sqlite3.Connection) -> bool:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            name TEXT,
            extension TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            sha256 TEXT,
            cliente_carpeta TEXT,
            area_probable TEXT,
            anio_probable TEXT,
            ruta_relativa TEXT,
            indexed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_text (
            file_id INTEGER PRIMARY KEY,
            text_source TEXT,
            text_preview TEXT,
            text_full TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
        """
    )
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
            USING fts5(path, name, cliente_carpeta, area_probable, text_preview, text_full)
            """
        )
        return True
    except sqlite3.OperationalError:
        return False


def drop_db(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS files_fts")
    conn.execute("DROP TABLE IF EXISTS file_text")
    conn.execute("DROP TABLE IF EXISTS files")
