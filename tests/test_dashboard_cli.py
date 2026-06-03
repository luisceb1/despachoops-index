from datetime import datetime
from pathlib import Path

import yaml
from openpyxl import load_workbook

from despachoops_index.cli import main
from despachoops_index.config import IndexOptions, load_app_config
from despachoops_index.indexer import build_index


def _write_cfg(tmp_path: Path, *, reports: Path | None = None) -> Path:
    data = tmp_path / "data"
    payload = {
        "scan_root": str(tmp_path / "Clientes"),
        "data_dir": str(data),
    }
    if reports is not None:
        payload["reports_dir"] = str(reports)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(payload), encoding="utf-8")
    return cfg_path


def _seed_db(root: Path, db: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "doc.txt").write_text("contenido", encoding="utf-8")
    build_index(IndexOptions(root=root, db_path=db, include_text=True))


def test_dashboard_without_output_creates_timestamped_xlsx(tmp_path: Path, monkeypatch):
    cfg_path = _write_cfg(tmp_path, reports=tmp_path / "reports")
    app = load_app_config(cfg_path)
    scan = tmp_path / "Clientes"
    scan.mkdir()
    db = app.index_db_path
    _seed_db(scan, db)

    fixed = datetime(2026, 6, 3, 19, 35, 0)
    monkeypatch.setattr(
        "despachoops_index.config.datetime",
        type("DT", (), {"now": staticmethod(lambda: fixed)}),
    )

    assert main(["--config", str(cfg_path), "dashboard"]) == 0
    expected = tmp_path / "reports" / "index_dashboard_20260603_193500.xlsx"
    assert expected.exists()
    wb = load_workbook(expected, read_only=True)
    assert "Resumen" in wb.sheetnames
    wb.close()


def test_dashboard_with_explicit_output(tmp_path: Path):
    cfg_path = _write_cfg(tmp_path, reports=tmp_path / "reports")
    app = load_app_config(cfg_path)
    scan = tmp_path / "Clientes"
    scan.mkdir()
    db = app.index_db_path
    _seed_db(scan, db)

    explicit = tmp_path / "reports" / "index_dashboard_20000.xlsx"
    assert main(["--config", str(cfg_path), "dashboard", "--output", str(explicit)]) == 0
    assert explicit.exists()
