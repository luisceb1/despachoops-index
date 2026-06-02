from __future__ import annotations

import fnmatch
import re
import unicodedata
from pathlib import Path

YEAR_STRICT = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

AREA_KEYWORDS = {
    "aeat": "Fiscal",
    "fiscal": "Fiscal",
    "irpf": "Fiscal",
    "renta": "Fiscal",
    "modelos": "Fiscal",
    "laboral": "Laboral",
    "tgss": "Laboral",
    "seguridad social": "Laboral",
    "contabilidad": "Contabilidad",
    "mercantil": "Mercantil",
    "judicial": "Judicial",
    "civil": "Civil",
    "penal": "Penal",
    "escrituras": "Escrituras",
    "notificaciones": "Administrativo",
}

TECHNICAL_FOLDERS = frozenset(
    {
        "aeat",
        "modelos",
        "modelos aeat",
        "seguridad social",
        "tgss",
        "irpf",
        "renta",
        "modeles",
        "backups",
        "plantillas",
    }
)


def normalize_token(value: str) -> str:
    rendered = unicodedata.normalize("NFKD", value)
    rendered = "".join(ch for ch in rendered if not unicodedata.combining(ch))
    return rendered.lower().strip()


def is_special_root(name: str, special_roots: tuple[str, ...]) -> bool:
    normalized = normalize_token(name)
    return any(normalize_token(root) == normalized for root in special_roots)


def is_technical_folder(name: str) -> bool:
    return normalize_token(name) in TECHNICAL_FOLDERS


def infer_client_folder(path: Path, scan_root: Path, special_roots: tuple[str, ...]) -> str:
    try:
        parts = path.relative_to(scan_root).parts[:-1]
    except ValueError:
        return ""
    if not parts:
        return ""
    if is_special_root(parts[0], special_roots):
        for part in reversed(parts):
            if not is_technical_folder(part) and not is_special_root(part, special_roots):
                return part
        return ""
    return parts[0]


def infer_area_from_path(path: Path) -> str:
    for part in path.parts:
        key = normalize_token(part)
        for token, area in AREA_KEYWORDS.items():
            if token in key:
                return area
    return "General"


def detect_year_from_path(path: Path) -> str:
    for part in path.parts:
        match = YEAR_STRICT.search(part)
        if match:
            return match.group(1)
    return ""


def matches_exclude_path(path: Path, patterns: tuple[str, ...]) -> bool:
    rendered = str(path).replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(rendered, pattern.replace("\\", "/")):
            return True
    return False
