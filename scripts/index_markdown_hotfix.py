from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_config_value(config_path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$")

    for line in config_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if not m:
            continue

        value = m.group(1).strip()

        # Quitar comentario YAML simple si lo hubiera.
        if " #" in value:
            value = value.split(" #", 1)[0].strip()

        # Quitar comillas externas.
        quoted = (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        )
        if quoted:
            value = value[1:-1]

        # Interpretar escapes típicos de YAML/Python: \\ -> \.
        # Esto convierte "\\\\Luiscp\\d\\..." en "\\Luiscp\d\..."
        # Normalizar barras escapadas del YAML sin romper rutas UNC.
        value = value.replace("\\\\", "\\")

        return value

    raise KeyError(f"No encuentro {key} en {config_path}")


def read_text_file(path: Path) -> str:
    last_error: Exception | None = None
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except Exception as e:
            last_error = e
    raise RuntimeError(f"No puedo leer {path}: {last_error}")


def clean_markdown(text: str) -> tuple[str, dict, list[str], str]:
    frontmatter = {}
    raw = text

    # Frontmatter YAML simple: --- ... ---
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm_raw = parts[1]
            raw = parts[2]
            for line in fm_raw.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip().strip('"').strip("'")

    # Markdown links [texto](url) -> texto
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)

    # Quitar marcas comunes, conservando contenido
    raw = re.sub(r"^#{1,6}\s*", "", raw, flags=re.MULTILINE)
    raw = raw.replace("**", "").replace("__", "").replace("`", "")
    raw = re.sub(r"^\s*[-*+]\s+", "- ", raw, flags=re.MULTILINE)

    lines = [ln.rstrip() for ln in raw.splitlines()]
    cleaned = "\n".join(lines).strip()

    headings = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            headings.append(line.strip().lstrip("#").strip())

    title = headings[0] if headings else ""
    return cleaned, frontmatter, headings, title


def normalize_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "cliente"


def classify_markdown(path: Path) -> str:
    name = path.name.lower()
    if name == "00_cliente.md":
        return "cliente_md"
    if name == "00_expediente_vivo.md":
        return "expediente_vivo_md"
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    return "unknown"


def client_from_path(path: Path, scan_root: Path, frontmatter: dict) -> tuple[str, str]:
    if frontmatter.get("client_key"):
        key = normalize_key(str(frontmatter["client_key"]))
        display = str(frontmatter.get("display_name") or frontmatter.get("cliente") or key)
        return key, display

    try:
        rel = path.relative_to(scan_root)
        first = rel.parts[0]
    except Exception:
        # Fallback robusto para UNC/case/path raros
        rel = os.path.relpath(str(path), str(scan_root))
        first = Path(rel).parts[0]

    display_name = first
    return normalize_key(display_name), display_name


def table_columns(cur: sqlite3.Cursor, table: str):
    return cur.execute(f"PRAGMA table_info({table})").fetchall()


def column_names(cur: sqlite3.Cursor, table: str) -> set[str]:
    return {row[1] for row in table_columns(cur, table)}


def default_for_col(colinfo):
    name = colinfo[1]
    typ = (colinfo[2] or "").upper()
    if name.lower() == "id" and colinfo[5]:
        return None
    if "INT" in typ:
        return 0
    if "REAL" in typ or "FLOA" in typ or "DOUB" in typ:
        return 0.0
    return ""


def ensure_aux_tables(cur: sqlite3.Cursor):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS file_metadata (
        file_id INTEGER PRIMARY KEY,
        kind TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY,
        client_key TEXT UNIQUE,
        display_name TEXT,
        source_path TEXT,
        first_seen_at TEXT,
        last_seen_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS client_markdown (
        id INTEGER PRIMARY KEY,
        client_id INTEGER,
        file_id INTEGER,
        md_kind TEXT,
        path TEXT,
        title TEXT,
        frontmatter_json TEXT,
        headings_json TEXT,
        text_preview TEXT,
        updated_at TEXT
    )
    """)


def upsert_file(cur: sqlite3.Cursor, path: Path, text: str) -> int:
    path_str = str(path)
    now = now_iso()
    stat = path.stat()
    name = path.name
    ext = path.suffix.lower()
    size = stat.st_size
    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat()

    existing = cur.execute(
        "SELECT id FROM files WHERE lower(path) = lower(?)",
        (path_str,),
    ).fetchone()

    fcols_info = table_columns(cur, "files")
    fcols = {row[1]: row for row in fcols_info}

    values = {}

    # Mapeos habituales
    for col in fcols:
        low = col.lower()
        if col == "id":
            continue
        elif low == "path":
            values[col] = path_str
        elif low in {"name", "filename", "file_name", "basename"}:
            values[col] = name
        elif low in {"extension", "ext", "suffix"}:
            values[col] = ext
        elif low in {"size", "size_bytes", "bytes"}:
            values[col] = size
        elif low in {"mtime", "modified_at", "last_modified"}:
            values[col] = mtime
        elif low in {"indexed_at", "updated_at", "created_at"}:
            values[col] = now
        elif low in {"read_error", "error"}:
            values[col] = ""
        elif low in {"has_text"}:
            values[col] = 1
        elif low in {"is_dir", "ignored"}:
            values[col] = 0

    # Rellenar NOT NULL sin default
    for colinfo in fcols_info:
        cid, name_col, typ, notnull, dflt, pk = colinfo
        if pk:
            continue
        if notnull and dflt is None and name_col not in values:
            values[name_col] = default_for_col(colinfo)

    if existing:
        file_id = int(existing[0])
        update_cols = [c for c in values if c != "path"]
        if update_cols:
            sql = "UPDATE files SET " + ", ".join(f"{c}=?" for c in update_cols) + " WHERE id=?"
            cur.execute(sql, [values[c] for c in update_cols] + [file_id])
        return file_id

    cols = list(values.keys())
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO files ({', '.join(cols)}) VALUES ({placeholders})"
    cur.execute(sql, [values[c] for c in cols])
    return int(cur.lastrowid)


def upsert_file_text(cur: sqlite3.Cursor, file_id: int, text: str):
    cols_info = table_columns(cur, "file_text")
    cols = {row[1] for row in cols_info}
    now = now_iso()
    preview = text[:4000]

    cur.execute("DELETE FROM file_text WHERE file_id = ?", (file_id,))

    values = {}
    for col in cols:
        low = col.lower()
        if col == "id":
            continue
        elif low == "file_id":
            values[col] = file_id
        elif low in {"text", "content", "body", "full_text", "extracted_text"}:
            values[col] = text
        elif low in {"text_preview", "preview", "snippet"}:
            values[col] = preview
        elif low in {"chars", "text_chars", "length"}:
            values[col] = len(text)
        elif low in {"source", "extractor"}:
            values[col] = "markdown"
        elif low in {"created_at", "updated_at", "indexed_at"}:
            values[col] = now
        elif low in {"read_error", "error"}:
            values[col] = ""

    for colinfo in cols_info:
        cid, name_col, typ, notnull, dflt, pk = colinfo
        if pk:
            continue
        if notnull and dflt is None and name_col not in values:
            values[name_col] = default_for_col(colinfo)

    insert_cols = list(values.keys())
    sql = f"INSERT INTO file_text ({', '.join(insert_cols)}) VALUES ({', '.join('?' for _ in insert_cols)})"
    cur.execute(sql, [values[c] for c in insert_cols])


def upsert_fts(cur: sqlite3.Cursor, file_id: int, path: Path, text: str):
    if not cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files_fts'").fetchone():
        return

    fts_cols = [row[1] for row in cur.execute("PRAGMA table_info(files_fts)").fetchall()]
    if not fts_cols:
        return

    try:
        cur.execute("DELETE FROM files_fts WHERE rowid = ?", (file_id,))
    except sqlite3.OperationalError:
        pass

    values = {}
    for col in fts_cols:
        low = col.lower()
        if low in {"file_id", "id"}:
            values[col] = file_id
        elif low in {"path"}:
            values[col] = str(path)
        elif low in {"name", "filename", "file_name"}:
            values[col] = path.name
        elif low in {"text", "content", "body", "full_text", "extracted_text"}:
            values[col] = text
        elif low in {"extension", "ext"}:
            values[col] = path.suffix.lower()

    if not values:
        return

    cols = list(values.keys())
    sql = f"INSERT INTO files_fts (rowid, {', '.join(cols)}) VALUES (?, {', '.join('?' for _ in cols)})"
    cur.execute(sql, [file_id] + [values[c] for c in cols])


def upsert_client(cur: sqlite3.Cursor, client_key: str, display_name: str, source_path: str) -> int:
    now = now_iso()
    row = cur.execute("SELECT id FROM clients WHERE client_key = ?", (client_key,)).fetchone()
    if row:
        client_id = int(row[0])
        cur.execute(
            "UPDATE clients SET display_name=?, source_path=?, last_seen_at=? WHERE id=?",
            (display_name, source_path, now, client_id),
        )
        return client_id

    cur.execute(
        "INSERT INTO clients (client_key, display_name, source_path, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
        (client_key, display_name, source_path, now, now),
    )
    return int(cur.lastrowid)


def upsert_client_markdown(
    cur: sqlite3.Cursor,
    client_id: int,
    file_id: int,
    kind: str,
    path: Path,
    title: str,
    frontmatter: dict,
    headings: list[str],
    text: str,
):
    now = now_iso()
    cur.execute("DELETE FROM client_markdown WHERE file_id = ?", (file_id,))
    cur.execute(
        """
        INSERT INTO client_markdown (
            client_id, file_id, md_kind, path, title,
            frontmatter_json, headings_json, text_preview, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            client_id,
            file_id,
            kind,
            str(path),
            title,
            json.dumps(frontmatter, ensure_ascii=False),
            json.dumps(headings, ensure_ascii=False),
            text[:2000],
            now,
        ),
    )
    cur.execute(
        "INSERT OR REPLACE INTO file_metadata (file_id, kind, updated_at) VALUES (?, ?, ?)",
        (file_id, kind, now),
    )


def export_contexts(cur: sqlite3.Cursor, data_dir: Path):
    out_dir = data_dir / "client_context"
    out_dir.mkdir(parents=True, exist_ok=True)

    clients = cur.execute(
        "SELECT id, client_key, display_name FROM clients ORDER BY client_key"
    ).fetchall()

    for client_id, client_key, display_name in clients:
        rows = cur.execute(
            """
            SELECT md_kind, path, title, text_preview, updated_at
            FROM client_markdown
            WHERE client_id = ?
            ORDER BY
                CASE md_kind
                    WHEN 'expediente_vivo_md' THEN 1
                    WHEN 'cliente_md' THEN 2
                    ELSE 3
                END,
                path
            """,
            (client_id,),
        ).fetchall()

        if not rows:
            continue

        payload = {
            "client_key": client_key,
            "display_name": display_name,
            "source": "despachoops-index",
            "updated_at": now_iso(),
            "markdown_files": [
                {
                    "kind": kind,
                    "path": path,
                    "title": title,
                    "preview": preview,
                    "updated_at": updated_at,
                }
                for kind, path, title, preview, updated_at in rows
            ],
            "facts": {},
            "relevant_documents": [],
        }

        (out_dir / f"{client_key}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    scan_root = Path(read_config_value(config_path, "scan_root"))
    data_dir = Path(read_config_value(config_path, "data_dir"))
    db = data_dir / "despacho_index.sqlite"

    print("scan_root:", scan_root)
    print("data_dir:", data_dir)
    print("db:", db)

    if not scan_root.exists():
        raise SystemExit(f"No existe scan_root: {scan_root}")
    if not db.exists():
        raise SystemExit(f"No existe SQLite: {db}")

    md_files: list[Path] = []
    for root, _, files in os.walk(scan_root):
        for filename in files:
            if filename.lower().endswith((".md", ".markdown")):
                md_files.append(Path(root) / filename)

    print("Markdown encontrados en disco:", len(md_files))

    con = sqlite3.connect(str(db))
    cur = con.cursor()
    ensure_aux_tables(cur)

    processed = 0
    errors = 0

    for path in md_files:
        try:
            raw = read_text_file(path)
            text, frontmatter, headings, title = clean_markdown(raw)
            if not title:
                title = path.stem

            kind = classify_markdown(path)
            client_key, display_name = client_from_path(path, scan_root, frontmatter)

            file_id = upsert_file(cur, path, text)
            upsert_file_text(cur, file_id, text)
            upsert_fts(cur, file_id, path, text)

            client_id = upsert_client(cur, client_key, display_name, str(path.parent))
            upsert_client_markdown(
                cur=cur,
                client_id=client_id,
                file_id=file_id,
                kind=kind,
                path=path,
                title=title,
                frontmatter=frontmatter,
                headings=headings,
                text=text,
            )

            processed += 1
            if processed % 100 == 0:
                con.commit()
                print("Procesados:", processed)

        except Exception as e:
            errors += 1
            print(f"[ERROR] {path}: {e}")

    con.commit()
    export_contexts(cur, data_dir)
    con.commit()

    md_sqlite = cur.execute(
        """
        SELECT COUNT(*)
        FROM files
        WHERE lower(path) LIKE '%.md'
           OR lower(path) LIKE '%.markdown'
        """
    ).fetchone()[0]

    cliente_md = cur.execute(
        """
        SELECT COUNT(*)
        FROM file_metadata
        WHERE kind = 'cliente_md'
        """
    ).fetchone()[0]

    expediente_md = cur.execute(
        """
        SELECT COUNT(*)
        FROM file_metadata
        WHERE kind = 'expediente_vivo_md'
        """
    ).fetchone()[0]

    contexts = len(list((data_dir / "client_context").glob("*.json")))

    print()
    print("OK")
    print("Markdown procesados:", processed)
    print("Errores:", errors)
    print("Markdown en SQLite:", md_sqlite)
    print("cliente_md:", cliente_md)
    print("expediente_vivo_md:", expediente_md)
    print("client_context JSON:", contexts)


if __name__ == "__main__":
    main()