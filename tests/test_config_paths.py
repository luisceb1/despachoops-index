from datetime import datetime
from pathlib import Path

import yaml

from despachoops_index.cli import main
from despachoops_index.config import load_app_config


def test_load_shared_dirs_from_yaml(tmp_path: Path):
    index = tmp_path / "Index"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "shared_output_dir": str(index),
                "shared_reports_dir": str(index / "reports"),
                "shared_latest_dir": str(index / "latest"),
            }
        ),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.shared_output_dir == index
    assert app.shared_reports_dir == index / "reports"
    assert app.shared_latest_dir == index / "latest"
    assert app.reports_dir == app.shared_reports_dir


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
    assert app.shared_reports_dir == index / "reports"
    assert app.shared_latest_dir == index / "latest"


def test_legacy_reports_dir_maps_to_shared_reports(tmp_path: Path):
    reports = tmp_path / "reports_share"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "reports_dir": str(reports),
            }
        ),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.shared_reports_dir == reports


def test_default_shared_dirs_when_omitted(tmp_path: Path):
    data = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({"scan_root": str(tmp_path / "Clientes"), "data_dir": str(data)}),
        encoding="utf-8",
    )
    app = load_app_config(cfg_path)
    assert app.shared_reports_dir == data / "reports"
    assert app.shared_latest_dir == data / "latest"


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
        payload["shared_reports_dir"] = str(reports)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(payload), encoding="utf-8")
    return cfg_path


def test_init_creates_shared_output_dirs(tmp_path: Path):
    index = tmp_path / "Index"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "scan_root": str(tmp_path / "Clientes"),
                "data_dir": str(tmp_path / "data"),
                "shared_reports_dir": str(index / "reports"),
                "shared_latest_dir": str(index / "latest"),
            }
        ),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg_path), "init"]) == 0
    assert (index / "reports").is_dir()
    assert (index / "latest").is_dir()
    assert (tmp_path / "data" / "logs").is_dir()
    assert (tmp_path / "data" / "ocr_cache").is_dir()
