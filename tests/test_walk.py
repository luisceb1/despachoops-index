import sqlite3
from pathlib import Path

import yaml

from despachoops_index.config import IndexOptions, ScanFilters, load_app_config
from despachoops_index.indexer import build_index
from despachoops_index.walk import iter_scan_files, iter_scan_paths, skip_reason


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


def test_walk_skips_web_noise(tmp_path: Path):
    root = tmp_path / "scan"
    web = root / "cliente" / "descarga" / "css"
    web.mkdir(parents=True)
    (root / "expediente.pdf").write_bytes(b"%PDF-1.4")
    (web / "theme.css").write_text("body{}", encoding="utf-8")
    (root / "logo.gif").write_bytes(b"GIF89a")
    js_dir = root / "descarga" / "js"
    js_dir.mkdir(parents=True)
    (js_dir / "app.js").write_text("console.log(1)", encoding="utf-8")
    img_dir = root / "assets" / "css" / "images"
    img_dir.mkdir(parents=True)
    (img_dir / "icon.png").write_bytes(b"\x89PNG")

    filters = ScanFilters(
        exclude_path_patterns=(
            "*/descarga/css/*",
            "*/descarga/js/*",
            "*/css/images/*",
        ),
        exclude_extensions=(".png",),
    )
    names = {p.name for p in iter_scan_paths(root, filters, scan_root=root)}
    assert "expediente.pdf" in names
    assert "theme.css" not in names
    assert "logo.gif" not in names
    assert "app.js" not in names
    assert "icon.png" not in names


def test_excludes_nested_descarga_css_images_path(tmp_path: Path):
    root = tmp_path / "docs"
    nested = root / "descarga" / "css" / "images"
    nested.mkdir(parents=True)
    asset = nested / "ajax-loader.gif"
    asset.write_bytes(b"GIF89a")
    (root / "contrato.txt").write_text("hola", encoding="utf-8")

    filters = ScanFilters(
        exclude_path_patterns=("*/descarga/css/*", "*/css/images/*"),
        exclude_extensions=(".gif", ".css", ".js"),
    )
    skip, reason = skip_reason(asset, filters, scan_root=root)
    assert skip is True
    assert reason in {"ruta_ignorada", "extension_ruido"}

    db = tmp_path / "index.sqlite"
    opts = IndexOptions(
        root=root,
        db_path=db,
        exclude_path_patterns=filters.exclude_path_patterns,
        exclude_extensions=filters.exclude_extensions,
    )
    build_index(opts)
    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM files").fetchall()}
    conn.close()
    assert "contrato.txt" in names
    assert "ajax-loader.gif" not in names


def test_indexer_uses_exclude_extensions(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "contrato.txt").write_text("texto", encoding="utf-8")
    (root / "bundle.js").write_text("// noise", encoding="utf-8")

    db = tmp_path / "index.sqlite"
    build_index(IndexOptions(root=root, db_path=db))
    names = {p.name for p in iter_scan_paths(root, IndexOptions(root=root, db_path=db).to_scan_filters(), scan_root=root)}
    assert "contrato.txt" in names
    assert "bundle.js" not in names

    conn = sqlite3.connect(db)
    indexed = {r[0] for r in conn.execute("SELECT name FROM files").fetchall()}
    conn.close()
    assert "contrato.txt" in indexed
    assert "bundle.js" not in indexed
