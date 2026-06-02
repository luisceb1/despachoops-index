from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from despachoops_index.config import AppConfig
from despachoops_index.hashutil import file_sha256
from despachoops_index.llm.ollama_client import OllamaClient, profile_to_client
from despachoops_index.night_window import inside_window
from despachoops_index.safety import assert_writable_data_path


@dataclass(frozen=True)
class LlmEnrichmentResult:
    processed: int
    enriched: int
    skipped: int
    errors: int
    outside_window: bool
    disabled: bool
    preflight_failed: str = ""


def run_llm_enrichment(config: AppConfig, *, force: bool = False, now: datetime | None = None) -> LlmEnrichmentResult:
    llm = config.llm
    if not llm.enabled:
        return LlmEnrichmentResult(0, 0, 0, 0, False, True)
    current = now or datetime.now()
    if not force and not inside_window(current.time(), config.night_window_start, config.night_window_end):
        return LlmEnrichmentResult(0, 0, 0, 0, True, False)
    if not config.index_db_path.exists():
        return LlmEnrichmentResult(0, 0, 0, 0, False, False, "indice_no_existe")

    client = OllamaClient(profile_to_client(llm.profile))
    ok, msg = client.preflight()
    if not ok:
        return LlmEnrichmentResult(0, 0, 0, 0, False, False, msg)

    candidates = _candidates(config)
    enriched = skipped = errors = processed = 0
    for row in candidates:
        if llm.max_files_per_run > 0 and processed >= llm.max_files_per_run:
            break
        processed += 1
        text = _text_for(row, config)
        if len(text) < llm.min_text_chars:
            _save(config, int(row["id"]), "omitido_sin_texto", llm.profile.model)
            skipped += 1
            continue
        prompt = (
            f"Ruta: {row['path']}\nNombre: {row['name']}\n"
            f"Extensión: {row['extension']}\n\nExtracto:\n{text[:llm.text_chars_for_prompt]}"
        )
        result = client.chat_json(prompt)
        if result.error:
            _save(config, int(row["id"]), "error", llm.profile.model, error=result.error)
            errors += 1
            continue
        parsed, perr = _parse_json(result.content)
        if perr:
            _save(config, int(row["id"]), "error", llm.profile.model, error=perr)
            errors += 1
            continue
        _save(
            config, int(row["id"]), "ok", llm.profile.model,
            tipo=parsed.get("tipo_documental", ""),
            area=parsed.get("area", ""),
            resumen=parsed.get("resumen", ""),
            keywords=json.dumps(parsed.get("palabras_clave") or [], ensure_ascii=False),
            confianza=str(parsed.get("confianza", "")),
            revision=1 if parsed.get("necesita_revision") else 0,
        )
        enriched += 1

    if llm.release_model_after_batch and processed:
        client.release_model()
    return LlmEnrichmentResult(processed, enriched, skipped, errors, False, False)


def count_llm_pending(config: AppConfig) -> int:
    if not config.index_db_path.exists():
        return 0
    conn = sqlite3.connect(config.index_db_path)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM files f
            LEFT JOIN llm_enrichment l ON l.file_id = f.id
            WHERE l.file_id IS NULL
            """
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _candidates(config: AppConfig) -> list[sqlite3.Row]:
    conn = sqlite3.connect(config.index_db_path)
    conn.row_factory = sqlite3.Row
    limit = max(config.llm.max_files_per_run * 3, 60)
    try:
        return list(conn.execute(
            """
            SELECT f.id, f.path, f.name, f.extension,
                   COALESCE(t.text_full, '') AS text_full,
                   COALESCE(t.text_preview, '') AS text_preview
            FROM files f
            LEFT JOIN file_text t ON t.file_id = f.id
            LEFT JOIN llm_enrichment l ON l.file_id = f.id
            WHERE l.file_id IS NULL
            ORDER BY f.indexed_at DESC
            LIMIT ?
            """,
            (limit,),
        ))
    finally:
        conn.close()


def _text_for(row: sqlite3.Row, config: AppConfig) -> str:
    full = str(row["text_full"] or "").strip()
    preview = str(row["text_preview"] or "").strip()
    if full or preview:
        return full or preview
    path = Path(str(row["path"]))
    if path.is_file():
        cache = config.ocr_cache_dir / f"{file_sha256(path)}.txt"
        if cache.is_file():
            return cache.read_text(encoding="utf-8", errors="ignore")
    return ""


def _parse_json(content: str) -> tuple[dict, str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        s, e = content.find("{"), content.rfind("}")
        if s < 0:
            return {}, "json_invalido"
        try:
            data = json.loads(content[s : e + 1])
        except json.JSONDecodeError as exc:
            return {}, str(exc)
    return (data if isinstance(data, dict) else {}), ""


def _save(
    config: AppConfig,
    file_id: int,
    status: str,
    modelo: str,
    *,
    tipo: str = "",
    area: str = "",
    resumen: str = "",
    keywords: str = "[]",
    confianza: str = "",
    revision: int = 0,
    error: str = "",
) -> None:
    assert_writable_data_path(config.index_db_path, config.scan_root, config.data_dir)
    now = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(config.index_db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO llm_enrichment (
                file_id, tipo_documental, area_sugerida, resumen, palabras_clave,
                confianza, necesita_revision, modelo, status, error_message, enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, tipo, area, resumen[:500], keywords, confianza, revision, modelo, status, error, now),
        )
        conn.commit()
    finally:
        conn.close()
