from pathlib import Path

import yaml

from despachoops_index.config import load_app_config
from despachoops_index.walk import iter_scan_files


def test_walk_skips_git_and_temp(tmp_path: Path):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "ok.txt").write_text("a", encoding="utf-8")
    (root / "bad.tmp").write_bytes(b"")
    git = root / ".git"
    git.mkdir()
    (git / "x").write_text("y", encoding="utf-8")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.dump({"scan_root": str(root), "data_dir": str(tmp_path / "data")}),
        encoding="utf-8",
    )
    config = load_app_config(cfg_path)
    paths = [p.name for p in iter_scan_files(config)]
    assert "ok.txt" in paths
    assert "bad.tmp" not in paths
    assert "x" not in paths
