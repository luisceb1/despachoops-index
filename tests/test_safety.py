import pytest
from pathlib import Path

from indexops.safety import ReadOnlyViolation, assert_read_only_target


def test_blocks_write_under_scan_root(tmp_path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    scan.mkdir()
    data.mkdir()
    target = scan / "foo.txt"
    with pytest.raises(ReadOnlyViolation):
        assert_read_only_target(target, scan, data)


def test_allows_write_under_data_dir(tmp_path):
    scan = tmp_path / "Clientes"
    data = tmp_path / "data"
    scan.mkdir()
    data.mkdir()
    target = data / "index.sqlite"
    assert_read_only_target(target, scan, data)
