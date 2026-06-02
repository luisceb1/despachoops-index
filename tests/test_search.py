from pathlib import Path

from despachoops_index.config import IndexOptions
from despachoops_index.indexer import build_index
from despachoops_index.search import search


def test_search_by_name_and_text(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "modelo303.txt").write_text("declaracion modelo 303 iva", encoding="utf-8")
    (root / "otro.txt").write_text("sin relacion", encoding="utf-8")

    db = tmp_path / "index.sqlite"
    build_index(IndexOptions(root=root, db_path=db, include_text=True))

    by_name = search(db, "modelo303", limit=10)
    assert any("modelo303" in h.name for h in by_name)

    by_text = search(db, "iva", limit=10)
    assert any("303" in h.name for h in by_text)
