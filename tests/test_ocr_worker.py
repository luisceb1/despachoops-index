from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

from despachoops_index.config import load_app_config
from despachoops_index.ocr import OcrResult
from despachoops_index.ocr_worker import run_ocr_worker


def test_ocr_worker_processes_pdf(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    pdf = root / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({
            "scan_root": str(root),
            "data_dir": str(tmp_path / "data"),
            "ocr_worker_enabled": True,
            "night_window_start": "00:00",
            "night_window_end": "23:59",
            "max_files_per_ocr_run": 5,
        }),
        encoding="utf-8",
    )
    config = load_app_config(cfg_path)

    fake = OcrResult("texto ocr de prueba", "OCR_OK")
    with patch("despachoops_index.ocr_worker.extract_pdf_text_with_ocr", return_value=fake):
        result = run_ocr_worker(config, now=datetime(2026, 1, 1, 2, 0))

    assert result.processed >= 1
    cache_files = list(config.ocr_cache_dir.glob("*.txt"))
    assert cache_files
