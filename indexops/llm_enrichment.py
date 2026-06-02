from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from indexops.config import IndexConfig
from indexops.llm.ollama_client import OllamaClient, profile_to_client_config
from indexops.night_window import inside_night_window
from indexops.safety import assert_read_only_target

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmEnrichmentResult:
    processed: int
    enriched: int
    skipped: int
    errors: int
    outside_window: bool
    disabled: bool
    preflight_failed: str = ""


def run_llm_enrichment(
    config: IndexConfig,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> LlmEnrichmentResult:
    llm = config.llm
    if not llm.enabled:
        return LlmEnrichmentResult(0, 0, 0, 0, False, True)

    current = now or datetime.now()
    if not force and not inside_night_window(
        current.time(),
        config.night_window_start,
        config.night_window_end,
    ):
        return LlmEnrichmentResult(0, 0, 0, 0, True, False)

    assert_read_only_target(config.index_db_path, config.scan_root, config.data_dir)
    if not config.index_db_path.exists():
        return LlmEnrichmentResult(0, 0, 0, 0, False, False, "indice_no_existe")

    client = OllamaClient(profile_to_client_config(llm.profile))
    ok, reason = client.preflight()
    if not ok:
        return LlmEnrichmentResult(0, 0, 0, 0, False, False, reason)

    candidates = _select_candidates(config)
    enriched = skipped = errors = 0
    processed = 0

    for row in candidates:
        if llm.max_files_per_run > 0 and processed >= llm.max_files_per_run:
            break
        processed += 1
        text = _text_for_row(config, row)
        if len(text) < llm.min_text_chars:
            _save_enrichment(
                config,
                int(row["id"]),
                status="omitido_sin_texto",
                modelo=llm.profile.model,
            )
            skipped += 1
            continue

        prompt = _build_prompt(row, text[: llm.text_chars_for_prompt])
        result = client.chat_json(prompt)
        if result.error:
            _save_enrichment(
                config,
                int(row["id"]),
                status="error",
                modelo=llm.profile.model,
                error_message=result.error,
            )
            errors += 1
            continue

        parsed, parse_err = _parse_enrichment_json(result.content)
        if parse_err:
            _save_enrichment(
                config,
                int(row["id"]),
                status="error",
                modelo=llm.profile.model,
                error_message=parse_err,
            )
            errors += 1
            continue

        _save_enrichment(
            config,
            int(row["id"]),
            status="ok",
            modelo=llm.profile.model,
            tipo_documental=parsed.get("tipo_documental", ""),
            area_sugerida=parsed.get("area", ""),
            resumen=parsed.get("resumen", ""),
            palabras_clave=json.dumps(parsed.get("palabras_clave") or [], ensure_ascii=False),
            confianza=str(parsed.get("confianza", "")),
            necesita_revision="1" if parsed.get("necesita_revision") else "0",
        )
        enriched += 1

    if llm.release_model_after_batch and processed > 0:
        client.release_model()

    return LlmEnrichmentResult(processed, enriched, skipped, errors, False, False)


def _select_candidates(config: IndexConfig) -> list[sqlite3.Row]:
    conn = sqlite3.connect(config.index_db_path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_llm_table(conn)
        limit = config.llm.max_files_per_run if config.llm.max_files_per_run > 0 else 500
        return list(
            conn.execute(
                """
                SELECT f.id, f.path, f.name, f.extension, f.cliente_carpeta, f.area_probable,
                       f.sha256, COALESCE(t.text_full, '') AS text_full,
                       COALESCE(t.text_preview, '') AS text_preview
                FROM files f
                LEFT JOIN file_text t ON t.file_id = f.id
                LEFT JOIN llm_enrichment l ON l.file_id = f.id
                WHERE l.file_id IS NULL
                ORDER BY f.indexed_at DESC
                LIMIT ?
                """,
                (limit * 3,),
            )
        )
    finally:
        conn.close()


def _text_for_row(config: IndexConfig, row: sqlite3.Row) -> str:
    full = str(row["text_full"] or "").strip()
    preview = str(row["text_preview"] or "").strip()
    if full or preview:
        return full or preview
    sha = str(row["sha256"] or "").strip()
    if sha:
        cache = config.ocr_cache_dir / f"{sha}.txt"
        if cache.is_file():
            return cache.read_text(encoding="utf-8", errors="ignore")
    return ""


def _build_prompt(row: sqlite3.Row, text: str) -> str:
    return (
        f"Ruta: {row['path']}\n"
        f"Nombre archivo: {row['name']}\n"
        f"Cliente (carpeta): {row['cliente_carpeta']}\n"
        f"Área por ruta: {row['area_probable']}\n"
        f"Extensión: {row['extension']}\n\n"
        f"Extracto:\n{text}"
    )


def _parse_enrichment_json(content: str) -> tuple[dict, str]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return {}, "json_invalido"
        try:
            parsed = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            return {}, f"json_invalido:{exc}"
    if not isinstance(parsed, dict):
        return {}, "json_no_objeto"
    return parsed, ""


def _ensure_llm_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_enrichment (
            file_id INTEGER PRIMARY KEY,
            tipo_documental TEXT,
            area_sugerida TEXT,
            resumen TEXT,
            palabras_clave TEXT,
            confianza TEXT,
            necesita_revision INTEGER,
            modelo TEXT,
            status TEXT,
            error_message TEXT,
            enriched_at TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
        """
    )


def _save_enrichment(
    config: IndexConfig,
    file_id: int,
    *,
    status: str,
    modelo: str,
    tipo_documental: str = "",
    area_sugerida: str = "",
    resumen: str = "",
    palabras_clave: str = "[]",
    confianza: str = "",
    necesita_revision: str = "0",
    error_message: str = "",
) -> None:
    assert_read_only_target(config.index_db_path, config.scan_root, config.data_dir)
    now = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(config.index_db_path)
    try:
        _ensure_llm_table(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO llm_enrichment (
                file_id, tipo_documental, area_sugerida, resumen, palabras_clave,
                confianza, necesita_revision, modelo, status, error_message, enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                tipo_documental,
                area_sugerida,
                resumen[:500],
                palabras_clave,
                confianza,
                int(necesita_revision),
                modelo,
                status,
                error_message,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def count_llm_pending(config: IndexConfig) -> int:
    if not config.index_db_path.exists():
        return 0
    conn = sqlite3.connect(config.index_db_path)
    try:
        _ensure_llm_table(conn)
        row = conn.execute(
            """
            SELECT COUNT(*) FROM files f
            LEFT JOIN llm_enrichment l ON l.file_id = f.id
            WHERE l.file_id IS NULL
            """
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()
