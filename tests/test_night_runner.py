from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

from despachoops_index.config import load_app_config
from despachoops_index.indexer import IndexResult
from despachoops_index.llm_enrichment import LlmEnrichmentResult
from despachoops_index.night_runner import run_night_cycle
from despachoops_index.ocr_worker import OcrWorkerResult


def test_night_cycle_runs_pipeline(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("contenido nocturno", encoding="utf-8")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({
            "scan_root": str(root),
            "data_dir": str(tmp_path / "data"),
            "llm": {"enabled": False},
            "ocr_worker_enabled": True,
            "night_window_start": "00:00",
            "night_window_end": "23:59",
            "require_idle_minutes": 0,
            "max_files_per_index_run": 100,
            "max_files_per_ocr_run": 10,
        }),
        encoding="utf-8",
    )
    config = load_app_config(cfg_path)

    idx = IndexResult(config.index_db_path, 1, 1, 0, 0, 0, 1, True, False)
    ocr = OcrWorkerResult(0, 0, False, False, False)
    llm = LlmEnrichmentResult(0, 0, 0, 0, False, True)

    with patch("despachoops_index.night_runner.build_index", return_value=idx):
        with patch("despachoops_index.night_runner.run_ocr_worker", return_value=ocr):
            with patch("despachoops_index.night_runner.run_llm_enrichment", return_value=llm):
                result = run_night_cycle(config, force=True)

    assert result.ok
    assert result.indexed == 1
