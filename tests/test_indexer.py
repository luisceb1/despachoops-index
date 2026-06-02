import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from despachoops_index.config import IndexOptions, LONG_PATH_THRESHOLD
from despachoops_index.indexer import build_index, is_long_path


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "contrato.txt").write_text("texto estable contrato", encoding="utf-8")
    (root / "modelo303.txt").write_text("declaracion modelo 303 iva", encoding="utf-8")
    (root / "~$temporal.docx").write_bytes(b"x")
    (root / "Thumbs.db").write_bytes(b"x")
    sub = root / "cliente" / "Fiscal"
    sub.mkdir(parents=True)
    (sub / "nota.pdf").write_bytes(b"%PDF-1.4\n")
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "secret").write_text("no indexar", encoding="utf-8")
    return root


def test_index_creates_sqlite_and_does_not_modify_files(sample_root: Path, tmp_path: Path):
    f1 = sample_root / "contrato.txt"
    mtime_before = f1.stat().st_mtime_ns
    db = tmp_path / "data" / "index.sqlite"

    result = build_index(IndexOptions(root=sample_root, db_path=db, include_text=True))

    assert db.exists()
    assert result.indexed >= 3
    assert result.skipped_ignored >= 2
    assert f1.stat().st_mtime_ns == mtime_before

    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM files").fetchall()}
    ignored = conn.execute("SELECT COUNT(*) FROM ignored_files").fetchone()[0]
    conn.close()
    assert "contrato.txt" in names
    assert "secret" not in names
    assert ignored >= 2


def test_read_error_does_not_break_index(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "ok.txt").write_text("hola", encoding="utf-8")
    (root / "broken.pdf").write_bytes(b"not-a-pdf")

    db = tmp_path / "index.sqlite"
    with patch("despachoops_index.indexer._read_pdf", side_effect=OSError("lectura fallida")):
        result = build_index(IndexOptions(root=root, db_path=db, include_text=True))

    assert result.indexed == 2
    assert result.read_errors >= 1
    conn = sqlite3.connect(db)
    err_row = conn.execute(
        "SELECT read_error FROM files WHERE name = 'broken.pdf'"
    ).fetchone()
    conn.close()
    assert err_row and "lectura" in err_row[0].lower() or "read_error" in err_row[0]


def test_incremental_skips_unchanged_files(sample_root: Path, tmp_path: Path):
    db = tmp_path / "index.sqlite"
    first = build_index(
        IndexOptions(root=sample_root, db_path=db, include_text=True, incremental=False),
    )
    second = build_index(
        IndexOptions(root=sample_root, db_path=db, include_text=True, incremental=True),
    )
    assert first.indexed >= 1
    assert second.skipped_unchanged >= first.indexed


def test_index_respects_limit(sample_root: Path, tmp_path: Path):
    db = tmp_path / "index.sqlite"
    result = build_index(IndexOptions(root=sample_root, db_path=db, limit=2))
    assert result.indexed == 2
    assert result.limit_reached is True


def test_long_path_detection():
    assert is_long_path(LONG_PATH_THRESHOLD) is True
    assert is_long_path(LONG_PATH_THRESHOLD - 1) is False
    assert is_long_path(100) is False


def test_fts_table_created_with_text(sample_root: Path, tmp_path: Path):
    db = tmp_path / "index.sqlite"
    build_index(IndexOptions(root=sample_root, db_path=db, include_text=True))
    conn = sqlite3.connect(db)
    fts = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='files_fts'"
    ).fetchone()
    conn.close()
    assert fts is not None
