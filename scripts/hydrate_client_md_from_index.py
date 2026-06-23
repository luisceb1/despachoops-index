from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from preview_client_md_from_index import render_markdown


START = "<!-- DESPACHOOPS_INDEX_START -->"
END = "<!-- DESPACHOOPS_INDEX_END -->"


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


def normalize_name(value: str) -> str:
    value = value.lower()
    value = value.replace("ñ", "n")
    value = re.sub(r"[^\w]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def find_client_dir(scan_root: Path, client_name: str) -> Path | None:
    target = normalize_name(client_name)

    exact = scan_root / client_name
    if exact.is_dir():
        return exact

    candidates = []
    for p in scan_root.iterdir():
        if not p.is_dir():
            continue

        score = 0
        n = normalize_name(p.name)

        if n == target:
            score = 100
        elif target in n or n in target:
            score = 80
        else:
            target_parts = set(target.split())
            name_parts = set(n.split())
            overlap = len(target_parts & name_parts)
            if overlap:
                score = overlap * 10

        if score:
            candidates.append((score, p))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_client_md(client_dir: Path) -> Path:
    preferred = [
        client_dir / "00_CLIENTE.md",
        client_dir / "00 Cliente.md",
        client_dir / "cliente.md",
    ]

    for p in preferred:
        if p.exists():
            return p

    found = list(client_dir.glob("**/00_CLIENTE.md"))
    if found:
        found.sort(key=lambda p: len(p.parts))
        return found[0]

    return client_dir / "00_CLIENTE.md"


def replace_block(existing: str, block: str) -> str:
    block = block.strip()

    if START in existing and END in existing:
        pattern = re.compile(
            re.escape(START) + r".*?" + re.escape(END),
            re.DOTALL,
        )
        return pattern.sub(lambda _match: block, existing).rstrip() + "\n"

    return existing.rstrip() + "\n\n" + block + "\n"


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def hydrate_one(config_path: Path, json_path: Path, dry_run: bool = False) -> int:
    scan_root = Path(read_config_value(config_path, "scan_root"))

    context = json.loads(json_path.read_text(encoding="utf-8"))
    client_name = context.get("client_name") or ""
    if not client_name:
        print("ERROR: JSON sin client_name:", json_path)
        return 1

    client_dir = find_client_dir(scan_root, client_name)
    if not client_dir:
        print("ERROR: no encuentro carpeta de cliente:", client_name)
        return 1

    md_path = find_client_md(client_dir)
    block = render_markdown(context)

    if md_path.exists():
        existing = md_path.read_text(encoding="utf-8", errors="ignore")
    else:
        existing = f"# {client_name}\n"

    new_text = replace_block(existing, block)

    print("Cliente:", client_name)
    print("Carpeta:", client_dir)
    print("Markdown:", md_path)

    if dry_run:
        if normalize_newlines(existing) == normalize_newlines(new_text):
            print("DRY RUN: sin cambios")
        else:
            print("DRY RUN: habría cambios")
        print("")
        print(block)
        return 0

    if normalize_newlines(existing) == normalize_newlines(new_text):
        print("SIN CAMBIOS: no escribo y no creo backup")
        return 0

    if md_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = md_path.with_suffix(md_path.suffix + f".bak_index_{stamp}")
        shutil.copy2(md_path, backup)
        print("Backup:", backup)

    md_path.write_text(new_text, encoding="utf-8")
    print("OK escrito:", md_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    return hydrate_one(
        config_path=Path(args.config),
        json_path=Path(args.json_path),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())