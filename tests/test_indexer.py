import sqlite3
from pathlib import Path

from despachoops_index.config import IndexOptions
from despachoops_index.indexer import build_index, is_long_path


def test_index_creates_sqlite_and_does_not_modify_files(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    f1 = root / "contrato.txt"
    f1.write_text("texto estable", encoding="utf-8")
    junk = root / "~$temporal.docx"
    junk.write_bytes(b"x")
    mtime_before = f1.stat().st_mtime_ns

    db = tmp_path / "data" / "index.sqlite"
    result = build_index(
        IndexOptions(root=root, db_path=db, limit=0, include_text=True),
    )

    assert db.exists()
    assert result.indexed == 1
    assert result.skipped_ignored == 1
    assert f1.stat().st_mtime_ns == mtime_before

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT name, extension FROM files").fetchone()
    conn.close()
    assert row[0] == "contrato.txt"
    assert row[1] == ".txt"


def test_read_error_does_not_break_index(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "ok.txt").write_text("hola", encoding="utf-8")
    broken = root / "broken.pdf"
    broken.write_bytes(b"not-a-pdf")

    db = tmp_path / "index.sqlite"
    result = build_index(IndexOptions(root=root, db_path=db, include_text=True))
    assert result.indexed == 2
    assert result.read_errors >= 1


def test_long_path_detection():
    assert is_long_path(240) is True
    assert is_long_path(100) is False
