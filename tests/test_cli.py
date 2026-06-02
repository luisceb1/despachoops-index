from pathlib import Path

import yaml

from despachoops_index.cli import main


def test_cli_index_search_dashboard(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "buscar.txt").write_text("termino unico xyz123", encoding="utf-8")
    db = tmp_path / "index.sqlite"
    out = tmp_path / "dash.xlsx"

    assert main(["index", "--root", str(root), "--db", str(db), "--text"]) == 0
    assert db.exists()

    assert main(["search", "xyz123", "--db", str(db), "--limit", "5"]) == 0
    assert main(["dashboard", "--db", str(db), "--output", str(out)]) == 0
    assert out.exists()


def test_cli_doctor_with_config(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.dump({
            "scan_root": str(root),
            "data_dir": str(tmp_path / "data"),
            "llm": {"enabled": False},
        }),
        encoding="utf-8",
    )
    assert main(["--config", str(cfg), "doctor"]) == 0
