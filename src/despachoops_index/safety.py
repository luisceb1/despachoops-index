from __future__ import annotations

import os
from pathlib import Path


class ReadOnlyViolation(RuntimeError):
    pass


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _is_under(child: Path, parent: Path) -> bool:
    child_r = _safe_resolve(child)
    parent_r = _safe_resolve(parent)
    try:
        child_r.relative_to(parent_r)
        return True
    except ValueError:
        pass
    child_s = os.path.normcase(str(child_r))
    parent_s = os.path.normcase(str(parent_r))
    if child_s == parent_s:
        return True
    sep = "\\" if os.sep == "\\" else os.sep
    return child_s.startswith(parent_s.rstrip(sep) + sep)


def assert_writable_output_path(
    path: Path,
    scan_root: Path,
    allowed_roots: tuple[Path, ...] | list[Path],
    *,
    check_scan: bool = True,
) -> None:
    resolved = _safe_resolve(path)
    if check_scan:
        scan = _safe_resolve(scan_root)
        if _is_under(resolved, scan):
            raise ReadOnlyViolation(f"Escritura bloqueada sobre documentos: {resolved}")
    for root in allowed_roots:
        if _is_under(resolved, root):
            return
    allowed = ", ".join(str(_safe_resolve(r)) for r in allowed_roots)
    raise ReadOnlyViolation(
        f"Solo se escribe en rutas permitidas ({allowed}); rechazado: {resolved}"
    )


def assert_writable_data_path(path: Path, scan_root: Path, data_dir: Path) -> None:
    assert_writable_output_path(path, scan_root, (data_dir,))


def verify_scan_root(scan_root: Path) -> tuple[bool, str]:
    if not scan_root.exists():
        return False, f"No existe o no montado: {scan_root}"
    if not scan_root.is_dir():
        return False, f"No es carpeta: {scan_root}"
    try:
        next(os.scandir(scan_root))
    except StopIteration:
        return True, "Carpeta vacía (accesible)"
    except PermissionError:
        return False, f"Sin permiso: {scan_root}"
    except OSError as exc:
        return False, str(exc)
    return True, "OK"


def is_under_scan(path: Path, scan_root: Path) -> bool:
    return _is_under(path, scan_root)
