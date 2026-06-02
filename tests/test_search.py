from pathlib import Path

import pytest

from despachoops_index.config import IndexOptions
from despachoops_index.indexer import build_index
from despachoops_index.search import search


@pytest.fixture
def indexed_db(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "modelo303.txt").write_text("declaracion modelo 303 iva trimestral", encoding="utf-8")
    (root / "otro.txt").write_text("sin relacion", encoding="utf-8")
    (root / "factura.pdf").write_bytes(b"%PDF-1.4")
    db = tmp_path / "index.sqlite"
    build_index(IndexOptions(root=root, db_path=db, include_text=True))
    return db


def test_search_by_name(indexed_db: Path):
    hits = search(indexed_db, "modelo303", limit=10)
    assert any("modelo303" in h.name for h in hits)


def test_search_by_text(indexed_db: Path):
    hits = search(indexed_db, "iva", limit=10)
    assert any("303" in h.name for h in hits)


def test_search_by_extension(indexed_db: Path):
    hits = search(indexed_db, "", limit=50, extension="txt")
    assert hits
    assert all(h.extension == ".txt" for h in hits)


def test_search_empty_query_lists_files(indexed_db: Path):
    hits = search(indexed_db, "", limit=10)
    assert len(hits) >= 2
