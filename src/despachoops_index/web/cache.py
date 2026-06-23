from __future__ import annotations

import argparse
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe config: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def db_path_from_config(config: dict[str, Any]) -> Path:
    if config.get("index_db_path"):
        return Path(config["index_db_path"])
    data_dir = Path(config.get("data_dir", "C:/DespachoOpsData/Index"))
    return data_dir / "despacho_index.sqlite"


def normalize_search_text(value: str) -> str:
    value = str(value or "").lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def normalized_words(value: str) -> str:
    """
    Versión por palabras, útil para FTS:
    'Mateo Cebrián-Fraile' -> 'mateo cebrian fraile'
    """
    value = str(value or "").lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("ñ", "n")
    words = re.findall(r"[a-z0-9]+", value)
    return " ".join(words)


def rel_path_after_clientes(value: str) -> str:
    value = str(value or "")
    lower = value.lower()

    for needle in ["\\clientes\\", "/clientes/"]:
        pos = lower.find(needle)
        if pos >= 0:
            return value[pos + len(needle):]

    return value


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f"PRAGMA table_info({table})")]


def pick_col(cols: list[str], candidates: list[str]) -> str | None:
    lowered = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    return None


def build_base_sql(con: sqlite3.Connection) -> str:
    files_cols = columns(con, "files")

    file_id = pick_col(files_cols, ["id", "file_id"])
    path = pick_col(files_cols, ["path", "full_path"])
    name = pick_col(files_cols, ["name", "filename", "file_name"])
    extension = pick_col(files_cols, ["extension", "ext"])
    size_bytes = pick_col(files_cols, ["size_bytes", "size", "bytes"])
    mtime_iso = pick_col(files_cols, ["mtime_iso", "modified_iso", "mtime", "modified_at"])
    read_error = pick_col(files_cols, ["read_error", "error"])

    if not file_id or not path:
        raise RuntimeError("La tabla files no tiene columnas mínimas id/path")

    name_expr = f"f.{name}" if name else "f.path"
    ext_expr = f"f.{extension}" if extension else "''"
    size_expr = f"f.{size_bytes}" if size_bytes else "NULL"
    mtime_expr = f"f.{mtime_iso}" if mtime_iso else "NULL"
    err_expr = f"f.{read_error}" if read_error else "NULL"

    join = ""
    preview_expr = "NULL"
    full_expr = "NULL"

    if table_exists(con, "file_text"):
        text_cols = columns(con, "file_text")
        text_file_id = pick_col(text_cols, ["file_id", "id"])
        preview = pick_col(text_cols, ["text_preview", "preview", "snippet"])
        full = pick_col(text_cols, ["text_full", "text", "content", "body"])

        if text_file_id:
            join = f"LEFT JOIN file_text t ON t.{text_file_id} = f.{file_id}"
            preview_expr = f"t.{preview}" if preview else "NULL"
            full_expr = f"t.{full}" if full else "NULL"

    return f"""
        SELECT
            f.{file_id} AS id,
            f.{path} AS path,
            {name_expr} AS name,
            {ext_expr} AS extension,
            {size_expr} AS size_bytes,
            {mtime_expr} AS mtime_iso,
            {err_expr} AS read_error,
            {preview_expr} AS text_preview,
            {full_expr} AS text_full
        FROM files f
        {join}
    """


def rebuild_cache(db_path: Path) -> None:
    print(f"DB: {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")

    base_sql = build_base_sql(con)

    print("Borrando caché anterior...")
    con.execute("DROP TABLE IF EXISTS web_search_cache")
    con.execute("DROP TABLE IF EXISTS web_search_cache_fts")

    print("Creando tabla web_search_cache...")
    con.execute(
        """
        CREATE TABLE web_search_cache (
            id INTEGER PRIMARY KEY,
            path TEXT,
            relpath TEXT,
            name TEXT,
            extension TEXT,
            size_bytes INTEGER,
            mtime_iso TEXT,
            read_error TEXT,
            text_preview TEXT,
            text_full TEXT,
            norm_name TEXT,
            norm_relpath TEXT,
            norm_preview TEXT,
            words_name TEXT,
            words_relpath TEXT,
            words_preview TEXT,
            search_blob TEXT,
            has_text INTEGER
        )
        """
    )

    print("Leyendo documentos indexados...")
    rows = con.execute(base_sql).fetchall()
    total = len(rows)
    print(f"Documentos base: {total}")

    insert_sql = """
        INSERT INTO web_search_cache (
            id, path, relpath, name, extension, size_bytes, mtime_iso,
            read_error, text_preview, text_full,
            norm_name, norm_relpath, norm_preview,
            words_name, words_relpath, words_preview,
            search_blob, has_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch = []
    for i, row in enumerate(rows, start=1):
        path = row["path"] or ""
        relpath = rel_path_after_clientes(path)
        name = row["name"] or Path(path).name
        preview = row["text_preview"] or ""
        full = row["text_full"] or ""

        norm_name = normalize_search_text(name)
        norm_relpath = normalize_search_text(relpath)
        norm_preview = normalize_search_text(preview)

        words_name = normalized_words(name)
        words_relpath = normalized_words(relpath)
        words_preview = normalized_words(preview)

        compact_blob = " ".join(
            part for part in [
                norm_name,
                norm_relpath,
                norm_preview,
                words_name,
                words_relpath,
                words_preview,
            ]
            if part
        )

        has_text = 1 if (preview or full) else 0

        batch.append(
            (
                row["id"],
                path,
                relpath,
                name,
                row["extension"],
                row["size_bytes"],
                row["mtime_iso"],
                row["read_error"],
                preview,
                full,
                norm_name,
                norm_relpath,
                norm_preview,
                words_name,
                words_relpath,
                words_preview,
                compact_blob,
                has_text,
            )
        )

        if len(batch) >= 1000:
            con.executemany(insert_sql, batch)
            con.commit()
            print(f"Insertados {i}/{total}")
            batch.clear()

    if batch:
        con.executemany(insert_sql, batch)
        con.commit()
        print(f"Insertados {total}/{total}")

    print("Creando índices...")
    con.execute("CREATE INDEX idx_web_cache_extension ON web_search_cache(extension)")
    con.execute("CREATE INDEX idx_web_cache_kind ON web_search_cache(extension, has_text)")
    con.execute("CREATE INDEX idx_web_cache_mtime ON web_search_cache(mtime_iso)")
    con.execute("CREATE INDEX idx_web_cache_has_text ON web_search_cache(has_text)")
    con.execute("CREATE INDEX idx_web_cache_norm_name ON web_search_cache(norm_name)")
    con.execute("CREATE INDEX idx_web_cache_norm_relpath ON web_search_cache(norm_relpath)")

    print("Creando FTS...")
    con.execute(
        """
        CREATE VIRTUAL TABLE web_search_cache_fts
        USING fts5(
            search_blob,
            content='web_search_cache',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )

    con.execute(
        """
        INSERT INTO web_search_cache_fts(rowid, search_blob)
        SELECT id, search_blob
        FROM web_search_cache
        """
    )

    con.commit()

    count = con.execute("SELECT COUNT(*) FROM web_search_cache").fetchone()[0]
    fts_count = con.execute("SELECT COUNT(*) FROM web_search_cache_fts").fetchone()[0]

    con.close()

    print("OK")
    print(f"web_search_cache: {count}")
    print(f"web_search_cache_fts: {fts_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruye caché web de búsqueda")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    db_path = db_path_from_config(config)
    rebuild_cache(db_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())