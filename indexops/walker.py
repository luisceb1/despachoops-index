from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from indexops.config import IndexConfig
from indexops.path_signals import matches_exclude_path


def matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def iter_scan_files(config: IndexConfig):
    root = config.scan_root
    if not root.exists():
        return

    if not config.recursive:
        for path in sorted(root.iterdir()):
            if path.is_file() and _yield_file(path, config):
                yield path
        return

    excluded = {item.lower() for item in config.exclude_dirs}
    for dir_root, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d
            for d in dirs
            if d.lower() not in excluded and not matches_any(d, config.exclude_patterns)
        )
        for filename in sorted(files):
            path = Path(dir_root) / filename
            if _yield_file(path, config):
                yield path


def _yield_file(path: Path, config: IndexConfig) -> bool:
    if not path.is_file():
        return False
    if matches_any(path.name, config.exclude_patterns):
        return False
    if matches_exclude_path(path, config.exclude_path_patterns):
        return False
    return True
