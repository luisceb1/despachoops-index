from pathlib import Path

import pytest

from despachoops_index.safety import (
    ReadOnlyViolation,
    assert_writable_data_path,
    assert_writable_output_path,
    verify_scan_root,
)


def test_blocks_write_on_scan_root(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    scan.mkdir()
    data.mkdir()
    reports.mkdir()
    with pytest.raises(ReadOnlyViolation):
        assert_writable_output_path(scan / "doc.pdf", scan, (data, reports))


def test_allows_write_in_data_dir(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    scan.mkdir()
    data.mkdir()
    reports.mkdir()
    assert_writable_output_path(data / "index.sqlite", scan, (data, reports))
    assert_writable_data_path(data / "index.sqlite", scan, data)


def test_allows_write_in_reports_dir(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    scan.mkdir()
    data.mkdir()
    reports.mkdir()
    assert_writable_output_path(
        reports / "index_dashboard_20260603_193500.xlsx",
        scan,
        (data, reports),
    )


def test_rejects_path_outside_data_and_reports(tmp_path: Path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    reports = tmp_path / "reports"
    other = tmp_path / "elsewhere"
    scan.mkdir()
    data.mkdir()
    reports.mkdir()
    other.mkdir()
    with pytest.raises(ReadOnlyViolation):
        assert_writable_output_path(other / "hack.xlsx", scan, (data, reports))


def test_verify_scan_root_ok(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    ok, msg = verify_scan_root(root)
    assert ok and msg == "OK"


def test_verify_scan_root_missing(tmp_path: Path):
    ok, msg = verify_scan_root(tmp_path / "no_existe")
    assert not ok
