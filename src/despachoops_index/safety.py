from __future__ import annotations

import os
from pathlib import Path


class ReadOnlyViolation(RuntimeError):
    pass


def assert_writable_data_path(path: Path, scan_root: Path, data_dir: Path) -> None:
    resolved = path.resolve()
    scan = scan_root.resolve()
    data = data_dir.resolve()
    try:
        resolved.relative_to(scan)
        raise ReadOnlyViolation(f"Escritura bloqueada sobre documentos: {resolved}")
    except ValueError:
        pass
    try:
        resolved.relative_to(data)
        return
    except ValueError:
        pass
    raise ReadOnlyViolation(f"Solo se escribe en data_dir ({data}); rechazado: {resolved}")


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
    try:
        path.resolve().relative_to(scan_root.resolve())
        return True
    except (ValueError, OSError):
        return False
