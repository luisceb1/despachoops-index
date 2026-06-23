from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def read_config_value(config_path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$")

    for line in config_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if not m:
            continue

        value = m.group(1).strip()

        if " #" in value:
            value = value.split(" #", 1)[0].strip()

        quoted = (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        )
        if quoted:
            value = value[1:-1]

        return value.replace("\\\\", "\\")

    raise KeyError(f"No encuentro {key} en {config_path}")


def normalize(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("ñ", "n")
    value = re.sub(r"[^\w]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def find_client_dir(scan_root: Path, client_name: str) -> Path | None:
    target = normalize(client_name)

    exact = scan_root / client_name
    if exact.is_dir():
        return exact

    candidates = []

    for p in scan_root.iterdir():
        if not p.is_dir():
            continue

        name_norm = normalize(p.name)
        score = 0

        if name_norm == target:
            score = 100
        elif target in name_norm or name_norm in target:
            score = 80
        else:
            target_parts = set(target.split())
            name_parts = set(name_norm.split())
            overlap = len(target_parts & name_parts)
            if overlap:
                score = overlap * 10

        if score:
            candidates.append((score, p))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_expediente_dir(client_dir: Path, expediente: str, contains: str = "") -> Path | None:
    expediente_norm = normalize(expediente)
    contains_norm = normalize(contains)

    candidates: list[tuple[int, Path]] = []

    for p in client_dir.rglob("*"):
        if not p.is_dir():
            continue

        rel = p.relative_to(client_dir)
        rel_norm = normalize(str(rel))
        name_norm = normalize(p.name)

        score = 0

        if expediente_norm:
            if expediente_norm == name_norm:
                score += 100
            elif expediente_norm in rel_norm:
                score += 70
            elif expediente_norm in name_norm:
                score += 50

        if contains_norm:
            if contains_norm == name_norm:
                score += 120
            elif contains_norm in rel_norm:
                score += 90
            elif contains_norm in name_norm:
                score += 70
            else:
                score = 0

        if score:
            candidates.append((score, p))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], -len(x[1].parts)), reverse=True)
    return candidates[0][1]


def open_path(path: Path) -> None:
    os.startfile(str(path))  # Windows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--client", required=True)
    parser.add_argument("--expediente", default="")
    parser.add_argument("--contains", default="")
    parser.add_argument(
        "--target",
        choices=["cliente-md", "cliente-folder", "expediente-md", "expediente-folder"],
        default="cliente-md",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    scan_root = Path(read_config_value(config_path, "scan_root"))

    client_dir = find_client_dir(scan_root, args.client)
    if not client_dir:
        print("ERROR: no encuentro cliente:", args.client)
        return 1

    if args.target == "cliente-folder":
        print("Abriendo carpeta cliente:", client_dir)
        open_path(client_dir)
        return 0

    if args.target == "cliente-md":
        md = client_dir / "00_CLIENTE.md"
        if not md.exists():
            print("ERROR: no existe:", md)
            return 1

        print("Abriendo 00_CLIENTE.md:", md)
        open_path(md)
        return 0

    if not args.expediente:
        print("ERROR: para expediente-md o expediente-folder debes indicar --expediente")
        return 1

    expediente_dir = find_expediente_dir(
        client_dir=client_dir,
        expediente=args.expediente,
        contains=args.contains,
    )

    if not expediente_dir:
        print("ERROR: no encuentro expediente")
        print("Cliente:", client_dir)
        print("Expediente:", args.expediente)
        print("Contains:", args.contains)
        return 1

    if args.target == "expediente-folder":
        print("Abriendo carpeta expediente:", expediente_dir)
        open_path(expediente_dir)
        return 0

    md = expediente_dir / "00_EXPEDIENTE.md"
    if not md.exists():
        print("ERROR: no existe:", md)
        return 1

    print("Abriendo 00_EXPEDIENTE.md:", md)
    open_path(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())