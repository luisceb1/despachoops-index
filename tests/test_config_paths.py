from datetime import datetime
from pathlib import Path

import yaml

from despachoops_index.cli import main
from despachoops_index.config import load_app_config


def test_config_parses_latest_dir(tmp_path: Path):
    index = tmp_path / "Index"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "shared_output_dir": str(index),
                "reports_dir": str(index / "reports"),
                "latest_dir": str(index / "latest"),
            }
        ),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.reports_dir == index / "reports"
    assert app.latest_dir == index / "latest"
    assert app.latest_dashboard_path() == index / "latest" / "index_dashboard.xlsx"


def test_shared_dirs_derived_from_shared_output_dir(tmp_path: Path):
    index = tmp_path / "Index"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "shared_output_dir": str(index),
            }
        ),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.reports_dir == index / "reports"
    assert app.latest_dir == index / "latest"


def test_default_reports_and_latest_when_omitted(tmp_path: Path):
    data = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({"scan_root": str(tmp_path / "Clientes"), "data_dir": str(data)}),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.reports_dir == data / "reports"
    assert app.latest_dir == data / "latest"


def test_default_dashboard_path_uses_timestamp(tmp_path: Path):
    cfg_path = _write_cfg(tmp_path, reports=tmp_path / "reports")
    app = load_app_config(cfg_path)
    fixed = datetime(2026, 6, 3, 19, 35, 0)
    out = app.default_dashboard_path(now=fixed)
    assert out == tmp_path / "reports" / "index_dashboard_20260603_193500.xlsx"


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


def test_init_creates_reports_and_latest_dirs(tmp_path: Path):
    index = tmp_path / "Index"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "reports_dir": str(index / "reports"),
                "latest_dir": str(index / "latest"),
            }
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg_path), "init"]) == 0
    assert (index / "reports").is_dir()
    assert (index / "latest").is_dir()
    assert (tmp_path / "data" / "logs").is_dir()
    assert (tmp_path / "data" / "ocr_cache").is_dir()
