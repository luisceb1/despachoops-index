from pathlib import Path

import pytest

from despachoops_index.safety import ReadOnlyViolation, assert_writable_data_path, verify_scan_root


def test_blocks_write_on_scan_root(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    scan.mkdir()
    data.mkdir()
    with pytest.raises(ReadOnlyViolation):
        assert_writable_data_path(scan / "doc.pdf", scan, data)


def test_allows_write_in_data_dir(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    scan.mkdir()
    data.mkdir()
    assert_writable_data_path(data / "index.sqlite", scan, data)


def test_verify_scan_root_ok(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    ok, msg = verify_scan_root(root)
    assert ok and msg == "OK"


def test_verify_scan_root_missing(tmp_path: Path):
    ok, msg = verify_scan_root(tmp_path / "no_existe")
    assert not ok
