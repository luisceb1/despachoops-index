from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from despachoops_index.config import AppConfig, SKIP_DIRS, SKIP_NAME_PATTERNS


def iter_scan_files(config: AppConfig):
    root = config.scan_root
    if not root.exists():
        return
    excluded = {d.lower() for d in config.exclude_dirs} | {d.lower() for d in SKIP_DIRS}
    patterns = config.exclude_patterns + SKIP_NAME_PATTERNS
    for dir_root, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs
            if d.lower() not in excluded and not _match(d, patterns)
        )
        for name in sorted(files):
            path = Path(dir_root) / name
            if _should_yield(path, config, patterns):
                yield path


def _should_yield(path: Path, config: AppConfig, patterns: tuple[str, ...]) -> bool:
    if not path.is_file():
        return False
    if _match(path.name, patterns):
        return False
    if path.suffix.lower() in {".tmp", ".lock", ".crdownload", ".part"}:
        return False
    rendered = str(path).replace("\\", "/")
    for pat in config.exclude_path_patterns:
        if fnmatch.fnmatch(rendered, pat.replace("\\", "/")):
            return False
    return True


def _match(value: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(value, p) for p in patterns)
