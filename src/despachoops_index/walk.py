from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from despachoops_index.config import AppConfig, ScanFilters


def iter_scan_files(config: AppConfig):
    filters = ScanFilters(
        exclude_dirs=config.exclude_dirs,
        exclude_patterns=config.exclude_patterns,
        exclude_path_patterns=config.exclude_path_patterns,
        exclude_extensions=config.exclude_extensions,
    )
    yield from iter_scan_paths(config.scan_root, filters)


def iter_scan_paths(root: Path, filters: ScanFilters | None = None):
    f = filters or ScanFilters()
    if not root.exists():
        return
    excluded_dirs = f.merged_dirs()
    name_patterns = f.merged_name_patterns()
    for dir_root, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d
            for d in dirs
            if d.lower() not in excluded_dirs and not _fnmatch_any(d, name_patterns)
        )
        for name in sorted(files):
            path = Path(dir_root) / name
            skip, _ = skip_reason(path, f)
            if not skip:
                yield path


def skip_reason(path: Path, filters: ScanFilters) -> tuple[bool, str]:
    if not path.is_file():
        return True, "no_archivo"
    if _fnmatch_any(path.name, filters.merged_name_patterns()):
        return True, "patron_ignorado"
    ext = path.suffix.lower()
    if ext in {".tmp", ".lock", ".crdownload", ".part"}:
        return True, "extension_temporal"
    if ext in filters.merged_extensions():
        return True, "extension_ruido"
    rendered = str(path).replace("\\", "/").lower()
    for pat in filters.merged_path_patterns():
        if fnmatch.fnmatch(rendered, pat.replace("\\", "/").lower()):
            return True, "ruta_ignorada"
    return False, ""


def _fnmatch_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(value, p) for p in patterns)
