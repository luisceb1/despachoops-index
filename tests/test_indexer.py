import yaml
from pathlib import Path

from indexops.config import load_config
from indexops.indexer import build_index, search_index


def _config(tmp_path: Path, scan: Path, data: Path) -> Path:
    cfg = {
        "scan_root": str(scan),
        "data_dir": str(data),
        "recursive": True,
        "max_files_per_index_run": 0,
        "index_text_enabled": True,
        "index_hash_files": False,
        "exclude_dirs": [],
        "exclude_patterns": [],
        "special_roots": [],
        "exclude_path_patterns": [],
        "llm": {"enabled": False},
        "catalog_each_night_cycle": False,
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def test_build_and_search(tmp_path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    client = scan / "Cliente Test"
    client.mkdir(parents=True)
    (client / "contrato fiscal 2024.txt").write_text("modelo 303 iva", encoding="utf-8")
    cfg_path = _config(tmp_path, scan, data)
    config = load_config(cfg_path)
    result = build_index(config)
    assert result.inserted == 1
    hits = search_index(config, "303")
    assert len(hits) >= 1
