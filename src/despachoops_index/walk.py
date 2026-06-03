from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from despachoops_index.config import AppConfig, ScanFilters


def iter_scan_files(config: AppConfig):
    yield from iter_scan_paths(config.scan_root, config.to_scan_filters())


def iter_scan_paths(
    root: Path,
    filters: ScanFilters | None = None,
    *,
    scan_root: Path | None = None,
):
    f = filters or ScanFilters()
    base = (scan_root or root).resolve()
    if not root.exists():
        return
    excluded_dirs = f.merged_dirs()
    name_patterns = f.merged_name_patterns()
    for dir_root, dirs, files in os.walk(root):
        current = Path(dir_root)
        dirs[:] = sorted(
            d
            for d in dirs
            if d.lower() not in excluded_dirs
            and not _fnmatch_any(d, name_patterns)
            and not _should_prune_dir(current / d, f, base)
        )
        for name in sorted(files):
            path = Path(dir_root) / name
            skip, _ = skip_reason(path, f, scan_root=base)
            if not skip:
                yield path


def skip_reason(
    path: Path,
    filters: ScanFilters,
    *,
    scan_root: Path | None = None,
) -> tuple[bool, str]:
    if not path.is_file():
        return True, "no_archivo"
    if _fnmatch_any(path.name, filters.merged_name_patterns()):
        return True, "patron_ignorado"
    ext = path.suffix.lower()
    if ext in {".tmp", ".lock", ".crdownload", ".part"}:
        return True, "extension_temporal"
    if ext in filters.merged_extensions():
        return True, "extension_ruido"
    for rendered in _path_candidates(path, scan_root):
        for pat in filters.merged_path_patterns():
            if _matches_path_pattern(rendered, pat):
                return True, "ruta_ignorada"
    return False, ""


def _should_prune_dir(dir_path: Path, filters: ScanFilters, scan_root: Path) -> bool:
    if dir_path.name.lower() in filters.merged_dirs():
        return True
    if _fnmatch_any(dir_path.name, filters.merged_name_patterns()):
        return True
    for rendered in _path_candidates(dir_path, scan_root):
        for pat in filters.merged_path_patterns():
            if _matches_path_pattern(rendered, pat):
                return True
    return False


def _path_candidates(path: Path, scan_root: Path | None) -> tuple[str, ...]:
    absolute = _normalize_path_str(path.resolve())
    out = [absolute]
    if scan_root is not None:
        try:
            rel = path.resolve().relative_to(scan_root.resolve())
            out.append(_normalize_path_str(rel))
        except ValueError:
            pass
    return tuple(dict.fromkeys(out))


def _normalize_path_str(path: Path | str) -> str:
    return str(path).replace("\\", "/").lower()


def _matches_path_pattern(rendered: str, pat: str) -> bool:
    pat = pat.replace("\\", "/").lower()
    rendered = rendered.replace("\\", "/").lower()
    bare = rendered.lstrip("/")
    if fnmatch.fnmatch(bare, pat) or fnmatch.fnmatch(rendered, pat):
        return True
    # fnmatch * no cruza / en algunos casos; comprobar segmento de ruta
    if pat.startswith("*/") and pat.endswith("/*") and len(pat) > 3:
        needle = pat[1:-1]
        if needle in f"/{bare}/":
            return True
    return False


def _fnmatch_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(value, p) for p in patterns)
