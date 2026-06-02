from __future__ import annotations

import os
from pathlib import Path


class ReadOnlyViolation(RuntimeError):
    """Intento de escribir fuera del directorio de datos del índice."""


def assert_read_only_target(path: Path, scan_root: Path, data_dir: Path) -> None:
    """Garantiza que no se escribe sobre el árbol de clientes."""
    resolved = path.resolve()
    scan = scan_root.resolve()
    data = data_dir.resolve()
    try:
        resolved.relative_to(scan)
        raise ReadOnlyViolation(
            f"Operación de escritura bloqueada sobre el árbol indexado: {resolved}"
        )
    except ValueError:
        pass
    try:
        resolved.relative_to(data)
        return
    except ValueError:
        pass
    raise ReadOnlyViolation(
        f"Solo se permite escribir bajo data_dir ({data}); ruta rechazada: {resolved}"
    )


def safe_open_for_write(path: Path, scan_root: Path, data_dir: Path, *args, **kwargs):
    assert_read_only_target(path, scan_root, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open(*args, **kwargs)


def is_path_under_scan(path: Path, scan_root: Path) -> bool:
    try:
        path.resolve().relative_to(scan_root.resolve())
        return True
    except (ValueError, OSError):
        return False


def verify_scan_root_access(scan_root: Path) -> tuple[bool, str]:
    if not scan_root.exists():
        return False, f"No existe o no está montado: {scan_root}"
    if not scan_root.is_dir():
        return False, f"No es carpeta: {scan_root}"
    try:
        next(os.scandir(scan_root))
    except StopIteration:
        return True, "Carpeta vacía (accesible)"
    except PermissionError:
        return False, f"Sin permiso de lectura: {scan_root}"
    except OSError as exc:
        return False, f"Error de acceso: {exc}"
    return True, "OK"
