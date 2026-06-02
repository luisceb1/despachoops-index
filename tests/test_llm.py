import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from despachoops_index.config import _parse_llm, load_app_config
from despachoops_index.config import IndexOptions
from despachoops_index.indexer import build_index
from despachoops_index.llm.ollama_client import OllamaChatResult, OllamaClient
from despachoops_index.llm_enrichment import _parse_json, run_llm_enrichment


def test_parse_llm_config():
    cfg = _parse_llm({"enabled": True, "enrich": {"model": "qwen3:8b"}})
    assert cfg.enabled and cfg.profile.model == "qwen3:8b"


def test_parse_llm_json():
    raw = (
        '{"tipo_documental":"Factura","area":"Fiscal","resumen":"IVA",'
        '"palabras_clave":["303"],"confianza":0.9,"necesita_revision":false}'
    )
    data, err = _parse_json(raw)
    assert not err and data["tipo_documental"] == "Factura"


def test_llm_enrichment_saves_row(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "doc.txt").write_text(
        "modelo 303 iva declaracion trimestral " * 5,
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({
            "scan_root": str(root),
            "data_dir": str(data_dir),
            "llm": {
                "enabled": True,
                "max_files_per_run": 5,
                "min_text_chars": 20,
                "enrich": {"model": "test"},
            },
            "night_window_start": "00:00",
            "night_window_end": "23:59",
            "require_idle_minutes": 0,
        }),
        encoding="utf-8",
    )
    config = load_app_config(cfg_path)
    db = config.index_db_path
    build_index(IndexOptions(root=root, db_path=db, include_text=True))

    payload = json.dumps({
        "tipo_documental": "Modelo_303",
        "area": "Fiscal",
        "resumen": "Declaracion IVA",
        "palabras_clave": ["303"],
        "confianza": 0.9,
        "necesita_revision": False,
    })

    with patch.object(OllamaClient, "preflight", return_value=(True, "")):
        with patch.object(OllamaClient, "chat_json", return_value=OllamaChatResult(payload)):
            with patch.object(OllamaClient, "release_model"):
                result = run_llm_enrichment(config, force=True)

    assert result.enriched == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT tipo_documental, status FROM llm_enrichment"
    ).fetchone()
    conn.close()
    assert row[0] == "Modelo_303" and row[1] == "ok"
