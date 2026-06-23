from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchHit:
    score: int
    path: str
    name: str
    extension: str
    text_preview: str


def search(
    db_path: Path,
    query: str,
    *,
    limit: int = 20,
    extension: str = "",
) -> list[SearchHit]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = _collect_rows(conn, query, extension=extension)
        terms = [t.lower() for t in query.split() if t.strip()]
        hits = [_score(row, terms) for row in rows]
        if terms:
            hits = [h for h in hits if h.score > 0]
        hits.sort(key=lambda h: (-h.score, h.path.lower()))
        return hits[:limit]
    finally:
        conn.close()


def _collect_rows(conn: sqlite3.Connection, query: str, *, extension: str) -> list[sqlite3.Row]:
    fts_rows: list[sqlite3.Row] = []
    if query.strip() and _fts_available(conn):
        match = _fts_query(query)
        if match:
            try:
                fts_rows = list(
                    conn.execute(
                        """
                        SELECT f.path, f.name, f.extension,
                               COALESCE(t.text_preview, '') AS text_preview,
                               COALESCE(l.resumen, '') AS llm_resumen
                        FROM files_fts x
                        JOIN files f ON f.id = x.rowid
                        LEFT JOIN file_text t ON t.file_id = f.id
                        LEFT JOIN llm_enrichment l ON l.file_id = f.id AND l.status = 'ok'
                        WHERE files_fts MATCH ?
                        """,
                        (match,),
                    )
                )
            except sqlite3.OperationalError:
                fts_rows = []

    like = f"%{query.lower()}%"
    clauses = []
    params: list[str] = []
    if query.strip():
        clauses.append(
            "(LOWER(f.path) LIKE ? OR LOWER(f.name) LIKE ? "
            "OR LOWER(COALESCE(t.text_preview, '')) LIKE ? OR LOWER(COALESCE(t.text_full, '')) LIKE ?)"
        )
        params.extend([like, like, like, like])
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        clauses.append("LOWER(f.extension) = ?")
        params.append(ext.lower())

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    like_rows = list(
        conn.execute(
            f"""
            SELECT f.path, f.name, f.extension, COALESCE(t.text_preview, '') AS text_preview,
                   COALESCE(l.resumen, '') AS llm_resumen
            FROM files f
            LEFT JOIN file_text t ON t.file_id = f.id
            LEFT JOIN llm_enrichment l ON l.file_id = f.id AND l.status = 'ok'
            {where}
            """,
            params,
        )
    )

    merged: dict[str, sqlite3.Row] = {str(r["path"]): r for r in fts_rows}
    for row in like_rows:
        merged[str(row["path"])] = row
    return list(merged.values())


def _score(row: sqlite3.Row, terms: list[str]) -> SearchHit:
    name = str(row["name"] or "").lower()
    path = str(row["path"] or "").lower()
    llm = str(row["llm_resumen"] or "") if "llm_resumen" in row.keys() else ""
    preview = f"{row['text_preview'] or ''} {llm}".lower()
    ext = str(row["extension"] or "").lower()
    score = 0
    for term in terms:
        if term in name:
            score += 50
        if term in path:
            score += 20
        if term in preview:
            score += 10
        if term in ext:
            score += 5
    return SearchHit(
        score=score,
        path=str(row["path"] or ""),
        name=str(row["name"] or ""),
        extension=str(row["extension"] or ""),
        text_preview=str(row["text_preview"] or ""),
    )


def _fts_available(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='files_fts'"
    ).fetchone()
    return row is not None


def _fts_query(query: str) -> str:
    terms = []
    for term in query.split():
        cleaned = term.strip().replace('"', '""')
        if cleaned:
            terms.append(f'"{cleaned}"')
    return " OR ".join(terms)
