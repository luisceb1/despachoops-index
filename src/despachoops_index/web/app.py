from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import subprocess
import unicodedata
from urllib.parse import quote
from pathlib import Path
from starlette.responses import RedirectResponse
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse


APP_TITLE = "DespachoOps Index"


TYPE_EXTENSIONS = {
    "pdf": [".pdf"],
    "word": [".doc", ".docx", ".rtf", ".odt"],
    "excel": [".xls", ".xlsx", ".xlsm", ".csv", ".ods"],
    "imagen": [".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".bmp"],
    "zip": [".zip", ".rar", ".7z"],
    "texto": [".txt", ".md", ".xml"],
}


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
    """
    Normalizaci?n agresiva para b?squeda:
    - min?sculas
    - sin tildes
    - ? -> n
    - sin espacios
    - sin guiones
    - sin barras bajas
    - sin puntos
    - sin signos
    """
    value = str(value or "").lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("?", "n")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def search_tokens(value: str) -> list[str]:
    """
    Tokens normalizados, preservando b?squedas tipo:
    'Mateo Cebri?n Fraile' -> ['mateo', 'cebrian', 'fraile']
    """
    value = str(value or "").lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("?", "n")
    raw = re.findall(r"[a-z0-9]+", value)
    return [t for t in raw if t]


def connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base SQLite: {db_path}")

    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row

    # Funci?n SQL propia para b?squeda flexible:
    # NORM('Mateo Cebri?n') -> 'mateocebrian'
    con.create_function("NORM", 1, normalize_search_text)
    con.create_function("RELPATH", 1, rel_path_after_clientes)

    return con



def rel_path_after_clientes(value: str) -> str:
    """
    Devuelve la ruta relativa desde la carpeta Clientes.

    Evita que b?squedas como 'Cebrian' coincidan por la ra?z del despacho.

    Ejemplo:
    ruta completa hasta Clientes + IRPF\LuisCebrianFraile\doc.pdf
    -> IRPF\LuisCebrianFraile\doc.pdf
    """
    value = str(value or "")
    lower = value.lower()

    needles = [
        "\\clientes\\",
        "/clientes/",
    ]

    for needle in needles:
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
    try:
        return [row[1] for row in con.execute(f"PRAGMA table_info({table})")]
    except sqlite3.Error:
        return []


def pick_col(cols: list[str], candidates: list[str]) -> str | None:
    lowered = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    return None



def is_local_client(request: Request) -> bool:
    host = ""
    if request.client:
        host = request.client.host or ""
    return host in {"127.0.0.1", "::1", "localhost"}



def client_open_url(path: str, kind: str = "file") -> str:
    return f"despachoops-open://{kind}?path={quote(str(path or ''), safe='')}"


def h(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def js(value: Any) -> str:
    return json.dumps(str(value or ""))


def human_size(value: Any) -> str:
    try:
        size = int(value or 0)
    except Exception:
        return ""

    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(size)
    for unit in units:
        if v < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(v)} {unit}"
            return f"{v:.1f} {unit}"
        v /= 1024
    return str(size)


def tokenize_fts(q: str) -> list[str]:
    return re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_]+", q or "")


def make_fts_query(q: str) -> str:
    tokens = tokenize_fts(q)
    if not tokens:
        return ""
    return " AND ".join(f"{token}*" for token in tokens[:8])


def get_file_columns(con: sqlite3.Connection) -> dict[str, str | None]:
    cols = columns(con, "files")
    return {
        "id": pick_col(cols, ["id", "file_id"]),
        "path": pick_col(cols, ["path", "full_path"]),
        "name": pick_col(cols, ["name", "filename", "file_name"]),
        "extension": pick_col(cols, ["extension", "ext"]),
        "size_bytes": pick_col(cols, ["size_bytes", "size", "bytes"]),
        "mtime_iso": pick_col(cols, ["mtime_iso", "modified_iso", "mtime", "modified_at"]),
        "read_error": pick_col(cols, ["read_error", "error"]),
    }


def get_text_columns(con: sqlite3.Connection) -> dict[str, str | None]:
    if not table_exists(con, "file_text"):
        return {
            "file_id": None,
            "preview": None,
            "full": None,
        }

    cols = columns(con, "file_text")
    return {
        "file_id": pick_col(cols, ["file_id", "id"]),
        "preview": pick_col(cols, ["text_preview", "preview", "snippet"]),
        "full": pick_col(cols, ["text_full", "text", "content", "body"]),
    }


def base_select(con: sqlite3.Connection) -> str:
    fc = get_file_columns(con)
    tc = get_text_columns(con)

    if not fc["id"] or not fc["path"]:
        raise RuntimeError("La tabla files no tiene columnas mínimas id/path")

    name_expr = f"f.{fc['name']}" if fc["name"] else "f.path"
    ext_expr = f"f.{fc['extension']}" if fc["extension"] else "''"
    size_expr = f"f.{fc['size_bytes']}" if fc["size_bytes"] else "NULL"
    mtime_expr = f"f.{fc['mtime_iso']}" if fc["mtime_iso"] else "NULL"
    err_expr = f"f.{fc['read_error']}" if fc["read_error"] else "NULL"

    if table_exists(con, "file_text") and tc["file_id"]:
        preview_expr = f"t.{tc['preview']}" if tc["preview"] else "NULL"
        full_expr = f"t.{tc['full']}" if tc["full"] else "NULL"
        join = f"LEFT JOIN file_text t ON t.{tc['file_id']} = f.{fc['id']}"
    else:
        preview_expr = "NULL"
        full_expr = "NULL"
        join = ""

    return f"""
        SELECT
            f.{fc['id']} AS id,
            f.{fc['path']} AS path,
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


def make_filters(
    *,
    ext: str = "",
    has_text: str = "",
    client: str = "",
    folder: str = "",
    year: str = "",
    kind: str = "",
) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []

    ext = (ext or "").strip().lower().lstrip(".")
    has_text = (has_text or "").strip().lower()
    client = (client or "").strip()
    folder = (folder or "").strip()
    year = (year or "").strip()
    kind = (kind or "").strip().lower()

    if ext:
        where.append("LOWER(COALESCE(extension,'')) = ?")
        params.append(f".{ext}")

    if kind and kind in TYPE_EXTENSIONS:
        placeholders = ",".join("?" for _ in TYPE_EXTENSIONS[kind])
        where.append(f"LOWER(COALESCE(extension,'')) IN ({placeholders})")
        params.extend(TYPE_EXTENSIONS[kind])

    if has_text == "yes":
        where.append("(COALESCE(text_preview,'') <> '' OR COALESCE(text_full,'') <> '')")
    elif has_text == "no":
        where.append("(COALESCE(text_preview,'') = '' AND COALESCE(text_full,'') = '')")

    # IMPORTANTE:
    # Cliente y carpeta se buscan sobre RELPATH(path), no sobre path completo.
    # As? evitamos que 'Cebrian' coincida por la ra?z 'Cebrian y Fraile Abogados'.
    if client:
        client_norm = normalize_search_text(client)
        if client_norm:
            where.append("NORM(RELPATH(COALESCE(path,''))) LIKE ?")
            params.append(f"%{client_norm}%")

    if folder:
        folder_norm = normalize_search_text(folder)
        if folder_norm:
            where.append("NORM(RELPATH(COALESCE(path,''))) LIKE ?")
            params.append(f"%{folder_norm}%")

    if year:
        safe_year = re.sub(r"[^0-9]", "", year)[:4]
        if len(safe_year) == 4:
            where.append(
                "("
                "COALESCE(mtime_iso,'') LIKE ? OR "
                "RELPATH(COALESCE(path,'')) LIKE ? OR "
                "COALESCE(name,'') LIKE ? OR "
                "COALESCE(text_preview,'') LIKE ?"
                ")"
            )
            like = f"%{safe_year}%"
            params.extend([like, like, like, like])

    return where, params


def make_snippet(row: dict[str, Any], q: str) -> str:
    text = row.get("text_preview") or row.get("text_full") or ""
    text = str(text).replace("\r", " ").replace("\n", " ")
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text).strip()
    terms = tokenize_fts(q)

    if not terms:
        return h(text[:300])

    lower = text.lower()
    pos = -1
    for term in terms:
        pos = lower.find(term.lower())
        if pos >= 0:
            break

    if pos < 0:
        snippet = text[:300]
    else:
        start = max(0, pos - 130)
        end = min(len(text), pos + 260)
        snippet = text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet += "…"

    snippet = h(snippet)
    for term in terms[:6]:
        snippet = re.sub(
            re.escape(h(term)),
            lambda m: f"<mark>{m.group(0)}</mark>",
            snippet,
            flags=re.IGNORECASE,
        )

    return snippet



DOC_INTENTS = {
    "sentencia": {
        "query": ["sentencia", "sen", "fallo"],
        "positive": ["sentencia", "sen", "fallo"],
        "negative": [
            "demanda", "contestacion", "alegacion", "alegaciones",
            "escrito", "recurso", "providencia", "decreto", "auto",
            "diligencia", "notificacion", "acuse", "justificante",
        ],
    },
    "demanda": {
        "query": ["demanda"],
        "positive": ["demanda"],
        "negative": ["sentencia", "providencia", "decreto", "auto", "notificacion"],
    },
    "alegaciones": {
        "query": ["alegaciones", "alegacion"],
        "positive": ["alegaciones", "alegacion", "escritoalegaciones"],
        "negative": ["sentencia", "demanda", "providencia", "decreto"],
    },
    "recurso": {
        "query": ["recurso", "suplicacion", "apelacion", "reposicion"],
        "positive": ["recurso", "suplicacion", "apelacion", "reposicion"],
        "negative": ["sentencia", "demanda"],
    },
    "contrato": {
        "query": ["contrato"],
        "positive": ["contrato"],
        "negative": ["factura", "nomina", "sentencia"],
    },
    "factura": {
        "query": ["factura", "fra"],
        "positive": ["factura", "fra"],
        "negative": ["contrato", "sentencia", "demanda"],
    },
    "nomina": {
        "query": ["nomina", "nominas", "n?mina", "n?minas"],
        "positive": ["nomina", "nominas"],
        "negative": ["factura", "contrato", "sentencia"],
    },
    "escritura": {
        "query": ["escritura", "notaria", "protocolo"],
        "positive": ["escritura", "notaria", "protocolo"],
        "negative": ["sentencia", "demanda", "factura"],
    },
}


def detect_doc_intents(q: str) -> list[str]:
    q_norm = normalize_search_text(q)
    tokens = set(search_tokens(q))
    intents = []

    for intent, spec in DOC_INTENTS.items():
        for word in spec["query"]:
            word_norm = normalize_search_text(word)
            if word_norm in tokens or word_norm in q_norm:
                intents.append(intent)
                break

    return intents


def all_tokens_in(value: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    return all(token in value for token in tokens)


def any_token_in(value: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    return any(token in value for token in tokens)


def relevance_score(row: dict[str, Any], q: str) -> int:
    """
    Ranking jur?dico-documental.

    Prioriza:
    1. coincidencia fuerte en nombre de archivo;
    2. coincidencia fuerte en ruta relativa;
    3. tipo documental pedido en nombre/ruta;
    4. coincidencia en preview/texto corto;
    5. penaliza documentos de tipo contrario si el usuario pide un tipo claro.

    Ejemplo:
    'Manuela Ballesteros sentencia'
    debe priorizar SENTENCIA.pdf frente a demanda/alegaciones que solo mencionan a Manuela.
    """
    q = q or ""
    q_norm = normalize_search_text(q)
    tokens = search_tokens(q)

    name = str(row.get("name") or "")
    relpath = str(row.get("relpath") or rel_path_after_clientes(row.get("path") or ""))
    preview = str(row.get("text_preview") or "")

    name_norm = normalize_search_text(name)
    rel_norm = normalize_search_text(relpath)
    preview_norm = normalize_search_text(preview)

    score = 0

    # Coincidencia exacta/compacta de toda la b?squeda.
    if q_norm:
        if name_norm == q_norm:
            score += 2000
        if q_norm in name_norm:
            score += 1200
        if q_norm in rel_norm:
            score += 800
        if q_norm in preview_norm:
            score += 150

    # Tokens: nombre > ruta > preview.
    if tokens:
        if all_tokens_in(name_norm, tokens):
            score += 900
        if all_tokens_in(rel_norm, tokens):
            score += 650
        if all_tokens_in(preview_norm, tokens):
            score += 120

        for token in tokens:
            if token in name_norm:
                score += 90
            if token in rel_norm:
                score += 45
            if token in preview_norm:
                score += 6

    # Intenci?n documental: sentencia, demanda, recurso, etc.
    intents = detect_doc_intents(q)

    for intent in intents:
        spec = DOC_INTENTS[intent]
        positives = [normalize_search_text(x) for x in spec["positive"]]
        negatives = [normalize_search_text(x) for x in spec["negative"]]

        # Si el tipo documental aparece en nombre, much?simo peso.
        if any_token_in(name_norm, positives):
            score += 1600

        # Si aparece en ruta, bastante peso.
        if any_token_in(rel_norm, positives):
            score += 700

        # Si solo aparece en preview, algo, pero mucho menos.
        if any_token_in(preview_norm, positives):
            score += 120

        # Penalizaciones por tipo contrario en nombre/ruta.
        # Ejemplo: si pido sentencia, baja demanda/alegaciones/recurso.
        if any_token_in(name_norm, negatives):
            score -= 900

        if any_token_in(rel_norm, negatives):
            score -= 350

    # Heur?sticas espec?ficas para sentencias judiciales.
    if "sentencia" in intents:
        # Patrones judiciales frecuentes en nombre de archivo.
        judicial_name = name_norm

        if judicial_name.startswith("sen") or "sen" in judicial_name[:12]:
            score += 450

        if "sentenciadesestimatoria" in judicial_name:
            score += 1000

        if "sentenciaestimatoria" in judicial_name:
            score += 1000

        if "sentencia" in judicial_name:
            score += 1200

    # Archivos PDF suelen ser m?s probables para sentencia/demanda/recurso.
    ext = str(row.get("extension") or "").lower()
    if intents and ext == ".pdf":
        score += 80

    # Penaliza nombres gen?ricos si no contienen tipo documental.
    generic_names = [
        "documento", "doc", "esc", "anexo", "imagen", "scan", "nuevo documento"
    ]
    if any(g in name_norm for g in generic_names):
        score -= 80

    return score


def search_docs(
    con: sqlite3.Connection,
    *,
    q: str = "",
    limit: int = 50,
    ext: str = "",
    has_text: str = "",
    client: str = "",
    folder: str = "",
    year: str = "",
    kind: str = "",
) -> list[dict[str, Any]]:
    """
    Buscador v0.8:
    - Usa web_search_cache.
    - Recupera candidatos r?pidos.
    - Ordena por relevancia jur?dico-documental en Python.
    """
    limit = max(1, min(int(limit or 50), 200))
    q = (q or "").strip()

    deep_text = False
    if q.lower().startswith("texto:"):
        deep_text = True
        q = q[6:].strip()

    if not table_exists(con, "web_search_cache"):
        raise RuntimeError(
            "No existe web_search_cache. Ejecuta: "
            "python -m despachoops_index.web.cache --config config.yaml"
        )

    where: list[str] = []
    params: list[Any] = []

    ext = (ext or "").strip().lower().lstrip(".")
    has_text = (has_text or "").strip().lower()
    client = (client or "").strip()
    folder = (folder or "").strip()
    year = (year or "").strip()
    kind = (kind or "").strip().lower()

    if ext:
        where.append("LOWER(COALESCE(c.extension,'')) = ?")
        params.append(f".{ext}")

    if kind and kind in TYPE_EXTENSIONS:
        placeholders = ",".join("?" for _ in TYPE_EXTENSIONS[kind])
        where.append(f"LOWER(COALESCE(c.extension,'')) IN ({placeholders})")
        params.extend(TYPE_EXTENSIONS[kind])

    if has_text == "yes":
        where.append("c.has_text = 1")
    elif has_text == "no":
        where.append("c.has_text = 0")

    if client:
        client_norm = normalize_search_text(client)
        if client_norm:
            where.append("c.norm_relpath LIKE ?")
            params.append(f"%{client_norm}%")

    if folder:
        folder_norm = normalize_search_text(folder)
        if folder_norm:
            where.append("c.norm_relpath LIKE ?")
            params.append(f"%{folder_norm}%")

    if year:
        safe_year = re.sub(r"[^0-9]", "", year)[:4]
        if len(safe_year) == 4:
            like = f"%{safe_year}%"
            where.append(
                "("
                "COALESCE(c.mtime_iso,'') LIKE ? OR "
                "COALESCE(c.relpath,'') LIKE ? OR "
                "COALESCE(c.name,'') LIKE ? OR "
                "COALESCE(c.text_preview,'') LIKE ?"
                ")"
            )
            params.extend([like, like, like, like])

    query_where: list[str] = []
    query_params: list[Any] = []

    if q:
        q_lower = q.lower()
        q_norm = normalize_search_text(q)
        tokens = search_tokens(q)
        fts_query = make_fts_query(q)

        # FTS como generador de candidatos.
        if fts_query and table_exists(con, "web_search_cache_fts"):
            query_where.append(
                "c.id IN (SELECT rowid FROM web_search_cache_fts WHERE web_search_cache_fts MATCH ?)"
            )
            query_params.append(fts_query)

        # Coincidencia compacta.
        if q_norm:
            like_norm = f"%{q_norm}%"
            query_where.append(
                "("
                "c.norm_name LIKE ? OR "
                "c.norm_relpath LIKE ? OR "
                "c.norm_preview LIKE ?"
                ")"
            )
            query_params.extend([like_norm, like_norm, like_norm])

        # Literal.
        literal = f"%{q_lower}%"
        query_where.append(
            "("
            "LOWER(COALESCE(c.name,'')) LIKE ? OR "
            "LOWER(COALESCE(c.relpath,'')) LIKE ? OR "
            "LOWER(COALESCE(c.text_preview,'')) LIKE ?"
            ")"
        )
        query_params.extend([literal, literal, literal])

        # Todos los tokens en el mismo campo.
        if len(tokens) >= 2:
            same_field_groups = []
            for field in ["c.norm_name", "c.norm_relpath", "c.norm_preview"]:
                parts = []
                for token in tokens[:8]:
                    parts.append(f"{field} LIKE ?")
                    query_params.append(f"%{token}%")
                same_field_groups.append("(" + " AND ".join(parts) + ")")
            query_where.append("(" + " OR ".join(same_field_groups) + ")")

        elif len(tokens) == 1:
            token = tokens[0]
            like = f"%{token}%"
            query_where.append(
                "("
                "c.norm_name LIKE ? OR "
                "c.norm_relpath LIKE ? OR "
                "c.norm_preview LIKE ?"
                ")"
            )
            query_params.extend([like, like, like])

        # Texto completo solo en modo profundo.
        if deep_text:
            for token in tokens[:8]:
                query_where.append("LOWER(COALESCE(c.text_full,'')) LIKE ?")
                query_params.append(f"%{token}%")

    final_where = list(where)
    final_params = list(params)

    if query_where:
        final_where.append("(" + " OR ".join(query_where) + ")")
        final_params.extend(query_params)

    sql = """
        SELECT
            c.id,
            c.path,
            c.relpath,
            c.name,
            c.extension,
            c.size_bytes,
            c.mtime_iso,
            c.read_error,
            c.text_preview,
            c.text_full,
            c.norm_name,
            c.norm_relpath,
            c.norm_preview
        FROM web_search_cache c
    """

    if final_where:
        sql += " WHERE " + " AND ".join(final_where)

    # Recuperamos m?s candidatos que el l?mite visible y rankeamos en Python.
    candidate_limit = max(limit * 12, 300)
    candidate_limit = min(candidate_limit, 1200)

    sql += " LIMIT ?"
    final_params.append(candidate_limit)

    rows = con.execute(sql, final_params).fetchall()

    out = []
    for row in rows:
        d = dict(row)
        d["_relevance"] = relevance_score(d, q) if q else 0
        d["score"] = d["_relevance"]
        d["snippet"] = make_snippet(d, q)
        out.append(d)

    if q:
        out.sort(
            key=lambda d: (
                -int(d.get("_relevance") or 0),
                str(d.get("mtime_iso") or ""),
            ),
            reverse=False,
        )
    else:
        out.sort(key=lambda d: str(d.get("mtime_iso") or ""), reverse=True)

    return out[:limit]


def get_doc(con: sqlite3.Connection, doc_id: int) -> dict[str, Any] | None:
    base_sql = base_select(con)
    row = con.execute(f"SELECT * FROM ({base_sql}) b WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def local_client(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def render_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{h(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{
    font-family: system-ui, -apple-system, Segoe UI, sans-serif;
    margin: 24px;
    background: #f6f7f8;
    color: #111;
}}
.container {{
    max-width: 1280px;
    margin: 0 auto;
}}
.card {{
    background: white;
    border: 1px solid #ddd;
    border-radius: 12px;
    padding: 16px;
    margin: 12px 0;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(4, minmax(160px, 1fr));
    gap: 10px;
    margin-top: 10px;
}}
@media (max-width: 900px) {{
    .grid {{
        grid-template-columns: repeat(2, minmax(160px, 1fr));
    }}
}}
@media (max-width: 520px) {{
    .grid {{
        grid-template-columns: 1fr;
    }}
}}
input, select, button {{
    font-size: 15px;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid #bbb;
}}
input[type=text] {{
    width: 100%;
    box-sizing: border-box;
}}
button {{
    cursor: pointer;
    background: #111;
    color: white;
    border: 1px solid #111;
}}
button.secondary {{
    background: white;
    color: #111;
}}
a {{
    color: #0645ad;
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}
label {{
    font-size: 13px;
    color: #444;
}}
.path {{
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 12px;
    word-break: break-all;
    color: #333;
}}
.meta {{
    color: #666;
    font-size: 13px;
    margin-top: 4px;
}}
.snippet {{
    margin-top: 8px;
    color: #222;
    line-height: 1.35;
}}
mark {{
    background: #fff3a3;
    padding: 0 2px;
}}
.actions {{
    margin-top: 10px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}}
.header {{
    display:flex;
    justify-content:space-between;
    gap:16px;
    align-items:center;
}}
.small {{
    font-size: 13px;
    color:#666;
}}
.error {{
    color: #9b1c1c;
}}
.badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 999px;
    background: #eee;
    font-size: 12px;
    color: #333;
}}
</style>
<script>
async function copyText(text) {{
    await navigator.clipboard.writeText(text);
}}
</script>
</head>
<body>
<div class="container">
<div class="header">
<h1>{h(title)}</h1>
<div class="small"><a href="/">Inicio</a> · <a href="/health">Health</a></div>
</div>
{body}
</div>
</body>
</html>"""


def search_form(
    *,
    q: str = "",
    client: str = "",
    folder: str = "",
    year: str = "",
    kind: str = "",
    ext: str = "",
    has_text: str = "",
    limit: int = 50,
) -> str:
    def selected(value: str, current: str) -> str:
        return "selected" if value == current else ""

    return f"""
    <div class="card">
        <form action="/search" method="get">
            <label>Búsqueda general</label>
            <input type="text" name="q" value="{h(q)}" placeholder="B?squeda normal: Mateo Cebrian, IRPF, AEAT... | Profunda: texto: fogasa insolvencia" autofocus>

            <div class="grid">
                <div>
                    <label>Cliente / carpeta raíz</label>
                    <input type="text" name="client" value="{h(client)}" placeholder="Agrolosanz, Sergio, Pablo...">
                </div>
                <div>
                    <label>Carpeta contiene</label>
                    <input type="text" name="folder" value="{h(folder)}" placeholder="AEAT, Laboral, Juzgado, Renta...">
                </div>
                <div>
                    <label>Año</label>
                    <input type="text" name="year" value="{h(year)}" placeholder="2024">
                </div>
                <div>
                    <label>Extensión concreta</label>
                    <input type="text" name="ext" value="{h(ext)}" placeholder="pdf, docx, xlsx">
                </div>
                <div>
                    <label>Tipo</label>
                    <select name="kind">
                        <option value="" {selected("", kind)}>Todos</option>
                        <option value="pdf" {selected("pdf", kind)}>PDF</option>
                        <option value="word" {selected("word", kind)}>Word</option>
                        <option value="excel" {selected("excel", kind)}>Excel</option>
                        <option value="imagen" {selected("imagen", kind)}>Imagen</option>
                        <option value="zip" {selected("zip", kind)}>ZIP/RAR</option>
                        <option value="texto" {selected("texto", kind)}>Texto/XML</option>
                    </select>
                </div>
                <div>
                    <label>Texto</label>
                    <select name="has_text">
                        <option value="" {selected("", has_text)}>Todos</option>
                        <option value="yes" {selected("yes", has_text)}>Con texto</option>
                        <option value="no" {selected("no", has_text)}>Sin texto</option>
                    </select>
                </div>
                <div>
                    <label>Límite</label>
                    <input type="number" name="limit" value="{h(limit)}" min="1" max="200">
                </div>
                <div style="align-self:end">
                    <button type="submit">Buscar</button>
                </div>
            </div>
        </form>
    </div>
    """


def create_app(config_path: str) -> FastAPI:
    config = load_config(config_path)
    db_path = db_path_from_config(config)

    app = FastAPI(title=APP_TITLE)
    app.state.config_path = str(config_path)
    app.state.db_path = db_path

    @app.get("/health", response_class=HTMLResponse)
    def health() -> str:
        try:
            con = connect_ro(db_path)
            total = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            files_cols = columns(con, "files")
            has_fts = table_exists(con, "files_fts")
            has_text_table = table_exists(con, "file_text")
            con.close()
            body = f"""
            <div class="card">
                <h2>OK</h2>
                <p>Base SQLite: <span class="path">{h(db_path)}</span></p>
                <p>Total files: <strong>{h(total)}</strong></p>
                <p>files_fts: <strong>{h(has_fts)}</strong></p>
                <p>file_text: <strong>{h(has_text_table)}</strong></p>
                <p>Columnas files: <span class="path">{h(", ".join(files_cols))}</span></p>
            </div>
            """
        except Exception as exc:
            body = f"""
            <div class="card error">
                <h2>Error</h2>
                <p>{h(exc)}</p>
            </div>
            """
        return render_page(f"{APP_TITLE} — Health", body)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        body = search_form()
        body += f"""
        <div class="card small">
            <strong>Modo de b?squeda:</strong><br>
            Normal/r?pida: escribe directamente, por ejemplo <code>Mateo Cebrian</code> o <code>IRPF Luis Cebrian</code>.<br>
            Profunda/OCR: escribe <code>texto:</code> delante, por ejemplo <code>texto: requerimiento subsanacion demanda</code>.
        </div>
        <div class="card small">
            Base SQLite: <span class="path">{h(db_path)}</span><br>
            Solo lectura. No mueve, renombra ni modifica documentos.
        </div>
        <div class="card small">
            Ejemplos:
            <span class="badge">cliente: Agrolosanz · carpeta: AEAT</span>
            <span class="badge">cliente: Sergio · búsqueda: contrato alquiler</span>
            <span class="badge">tipo: PDF · año: 2024 · texto: sin texto</span>
        </div>
        """
        return render_page(APP_TITLE, body)

    @app.get("/search", response_class=HTMLResponse)
    def search(
        q: str = Query("", max_length=300),
        client: str = Query("", max_length=200),
        folder: str = Query("", max_length=200),
        year: str = Query("", max_length=10),
        kind: str = Query(""),
        ext: str = Query("", max_length=20),
        has_text: str = Query(""),
        limit: int = Query(50, ge=1, le=200),
    ) -> str:
        con = connect_ro(db_path)
        try:
            rows = search_docs(
                con,
                q=q,
                limit=limit,
                ext=ext,
                has_text=has_text,
                client=client,
                folder=folder,
                year=year,
                kind=kind,
            )
        finally:
            con.close()

        body = search_form(
            q=q,
            client=client,
            folder=folder,
            year=year,
            kind=kind,
            ext=ext,
            has_text=has_text,
            limit=limit,
        )

        active = []
        if q:
            active.append(f"búsqueda: {h(q)}")
        if client:
            active.append(f"cliente: {h(client)}")
        if folder:
            active.append(f"carpeta: {h(folder)}")
        if year:
            active.append(f"año: {h(year)}")
        if kind:
            active.append(f"tipo: {h(kind)}")
        if ext:
            active.append(f"extensión: {h(ext)}")
        if has_text:
            active.append(f"texto: {h(has_text)}")

        if active:
            body += '<div class="small">Filtros activos: ' + " · ".join(active) + "</div>"

        body += f'<div class="small">{len(rows)} resultado(s)</div>'

        for row in rows:
            path = str(row.get("path") or "")
            name = row.get("name") or os.path.basename(path)
            extv = row.get("extension") or ""
            size = human_size(row.get("size_bytes"))
            mtime = row.get("mtime_iso") or ""
            read_error = row.get("read_error") or ""
            snippet = row.get("snippet") or make_snippet(row, q)

            err_html = f'<div class="meta error">Error: {h(read_error)}</div>' if read_error else ""

            body += f"""
            <div class="card">
                <div>
                    <strong><a href="/doc/{h(row.get("id"))}">{h(name)}</a></strong>
                    <span class="badge">{h(extv)}</span>
                </div>
                <div class="path">{h(path)}</div>
                <div class="meta">{h(size)} · {h(mtime)}</div>
                {err_html}
                <div class="snippet">{snippet}</div>
                <div class="actions">
                    <button class="secondary" onclick='copyText({js(path)})'>Copiar ruta</button>
                    <button class="secondary" onclick='copyText({js(os.path.dirname(path))})'>Copiar carpeta</button>
                    <a href="/doc/{h(row.get("id"))}"><button class="secondary" type="button">Ficha</button></a>
                    <form method="post" action="/open-folder/{h(row.get("id"))}">
                        <button type="submit">Abrir carpeta</button>
                    </form>
                    <form method="post" action="/open-file/{h(row.get("id"))}">
                        <button type="submit">Abrir archivo</button>
                    </form>
                </div>
            </div>
            """

        return render_page(f"{APP_TITLE} — Buscar", body)

    @app.get("/doc/{doc_id}", response_class=HTMLResponse)
    def doc(doc_id: int) -> str:
        con = connect_ro(db_path)
        try:
            row = get_doc(con, doc_id)
        finally:
            con.close()

        if not row:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        path = str(row.get("path") or "")
        text_preview = row.get("text_preview") or ""
        text_full = row.get("text_full") or ""
        text = text_preview or str(text_full)[:5000]

        body = f"""
        <div class="card">
            <h2>{h(row.get("name") or os.path.basename(path))}</h2>
            <div class="path">{h(path)}</div>
            <div class="meta">
                ID: {h(row.get("id"))}<br>
                Extensión: {h(row.get("extension"))}<br>
                Tamaño: {h(human_size(row.get("size_bytes")))}<br>
                Modificado: {h(row.get("mtime_iso"))}<br>
                Read error: {h(row.get("read_error"))}
            </div>
            <div class="actions">
                <button class="secondary" onclick='copyText({js(path)})'>Copiar ruta</button>
                <button class="secondary" onclick='copyText({js(os.path.dirname(path))})'>Copiar carpeta</button>
                <form method="post" action="/open-folder/{h(row.get("id"))}">
                    <button type="submit">Abrir carpeta</button>
                </form>
                <form method="post" action="/open-file/{h(row.get("id"))}">
                    <button type="submit">Abrir archivo</button>
                </form>
            </div>
        </div>
        <div class="card">
            <h3>Texto / preview</h3>
            <div class="snippet">{h(text).replace(chr(10), "<br>")}</div>
        </div>
        """
        return render_page(f"{APP_TITLE} — Documento", body)

    @app.api_route("/open-folder/{doc_id}", methods=["GET", "POST"])
    def open_folder(doc_id: int, request: Request):
        con = connect_ro(db_path)
        try:
            row = get_doc(con, doc_id)
        finally:
            con.close()

        if not row:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        path = str(row.get("path") or "")
        if not path:
            raise HTTPException(status_code=400, detail="Ruta vac?a")

        folder = os.path.dirname(path)

        # Si el usuario est? en otro ordenador, abrir en el PC cliente mediante protocolo local.
        if not local_client(request):
            url = client_open_url(folder, "folder")
            body = f"""
            <!doctype html>
            <html lang="es">
            <head>
                <meta charset="utf-8">
                <title>Abriendo carpeta...</title>
            </head>
            <body>
                <p>Abriendo carpeta en este ordenador...</p>
                <p>Si no se abre, instala el abridor local DespachoOps en este PC.</p>
                <p><a href="{h(url)}">Abrir carpeta</a></p>
                <script>
                    window.location.href = {js(url)};
                    setTimeout(function() {{
                        window.location.href = "/doc/{doc_id}";
                    }}, 1500);
                </script>
            </body>
            </html>
            """
            return HTMLResponse(body)

        # Si estamos en Luiscp/local, abrir directamente en Luiscp.
        try:
            if os.path.isdir(folder):
                subprocess.Popen(["explorer", folder])
            else:
                subprocess.Popen(["explorer", "/select,", path])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo abrir Explorer: {exc}")

        return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


    @app.api_route("/open-file/{doc_id}", methods=["GET", "POST"])
    def open_file(doc_id: int, request: Request):
        con = connect_ro(db_path)
        try:
            row = get_doc(con, doc_id)
        finally:
            con.close()

        if not row:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        path = str(row.get("path") or "")
        if not path:
            raise HTTPException(status_code=400, detail="Ruta vac?a")

        # Si el usuario est? en otro ordenador, abrir en el PC cliente mediante protocolo local.
        if not local_client(request):
            url = client_open_url(path, "file")
            body = f"""
            <!doctype html>
            <html lang="es">
            <head>
                <meta charset="utf-8">
                <title>Abriendo archivo...</title>
            </head>
            <body>
                <p>Abriendo archivo en este ordenador...</p>
                <p>Si no se abre, instala el abridor local DespachoOps en este PC.</p>
                <p><a href="{h(url)}">Abrir archivo</a></p>
                <script>
                    window.location.href = {js(url)};
                    setTimeout(function() {{
                        window.location.href = "/doc/{doc_id}";
                    }}, 1500);
                </script>
            </body>
            </html>
            """
            return HTMLResponse(body)

        # Si estamos en Luiscp/local, abrir directamente en Luiscp.
        try:
            if os.path.exists(path):
                os.startfile(path)
            else:
                folder = os.path.dirname(path)
                if folder and os.path.isdir(folder):
                    subprocess.Popen(["explorer", folder])
                else:
                    raise FileNotFoundError(path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo abrir el archivo: {exc}")

        return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="DespachoOps Index — buscador web lite")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    app = create_app(args.config)

    import uvicorn

    print("DespachoOps Index Lite")
    print(f"Config: {args.config}")
    print(f"DB: {app.state.db_path}")
    print(f"URL: http://{args.host}:{args.port}")

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())