from pathlib import Path

import pytest

from despachoops_index.safety import (
    ReadOnlyViolation,
    assert_writable_data_path,
    assert_writable_output_path,
    verify_scan_root,
)


def _prod_like_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path, tuple[Path, ...]]:
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    index = tmp_path / "Index"
    reports = index / "reports"
    latest = index / "latest"
    for d in (scan, data, reports, latest):
        d.mkdir(parents=True, exist_ok=True)
    roots = (data, reports, latest)
    return scan, data, reports, latest, roots


def test_blocks_write_under_clientes_scan_root(tmp_path: Path):
    scan, _data, _reports, _latest, roots = _prod_like_tree(tmp_path)
    with pytest.raises(ReadOnlyViolation):
        assert_writable_output_path(scan / "doc.pdf", scan, roots)


def test_allows_write_in_data_dir(tmp_path: Path):
    scan, data, _reports, _latest, roots = _prod_like_tree(tmp_path)
    assert_writable_output_path(data / "index.sqlite", scan, roots)
    assert_writable_data_path(data / "index.sqlite", scan, data)


def test_allows_write_in_shared_reports_dir(tmp_path: Path):
    scan, _data, reports, _latest, roots = _prod_like_tree(tmp_path)
    assert_writable_output_path(
        reports / "index_dashboard_20260603_193500.xlsx",
        scan,
        roots,
    )


def test_allows_write_in_shared_latest_dir(tmp_path: Path):
    scan, _data, _reports, latest, roots = _prod_like_tree(tmp_path)
    assert_writable_output_path(latest / "index_dashboard.xlsx", scan, roots)


def test_rejects_path_outside_allowed_roots(tmp_path: Path):
    scan, _data, _reports, _latest, roots = _prod_like_tree(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(ReadOnlyViolation):
        assert_writable_output_path(other / "hack.xlsx", scan, roots)


def test_verify_scan_root_ok(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    ok, msg = verify_scan_root(root)
    assert ok and msg == "OK"


def test_verify_scan_root_missing(tmp_path: Path):
    ok, msg = verify_scan_root(tmp_path / "no_existe")
    assert not ok
