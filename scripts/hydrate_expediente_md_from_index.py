from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from preview_expediente_md_from_index import (
    START,
    END,
    render_expediente_markdown,
)


RESULT_PREFIX = "__DESPACHOOPS_RESULT_JSON__="


def emit_result(payload: dict, json_result: bool) -> None:
    if json_result:
        print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False))


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


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def replace_block(existing: str, block: str) -> str:
    block = block.strip()

    if START in existing and END in existing:
        pattern = re.compile(
            re.escape(START) + r".*?" + re.escape(END),
            re.DOTALL,
        )
        return pattern.sub(lambda _match: block, existing).rstrip() + "\n"

    return existing.rstrip() + "\n\n" + block + "\n"


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


def find_expediente_dir(
    client_dir: Path,
    expediente: str,
    contains: str = "",
) -> Path | None:
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


def find_expediente_md(expediente_dir: Path) -> Path:
    preferred = [
        expediente_dir / "00_EXPEDIENTE.md",
        expediente_dir / "00 Expediente.md",
        expediente_dir / "expediente.md",
    ]

    for p in preferred:
        if p.exists():
            return p

    return expediente_dir / "00_EXPEDIENTE.md"


def initial_expediente_md(
    client_name: str,
    expediente: str,
    contains: str,
    expediente_dir: Path,
) -> str:
    title = contains or expediente or expediente_dir.name

    return f"""# {title}

## Datos del expediente

| Campo | Valor |
| --- | --- |
| Cliente | {client_name} |
| Expediente | {title} |
| Estado | activo |
| Responsable |  |
| Materia |  |
| Fecha alta | {datetime.now().strftime("%Y-%m-%d")} |
| Ruta | {expediente_dir} |

## Resumen manual


## Próxima actuación


## Notas

"""


def hydrate_one(
    config_path: Path,
    json_path: Path,
    expediente: str,
    contains: str = "",
    dry_run: bool = False,
    json_result: bool = False,
) -> int:
    payload = {
        "ok": False,
        "changed": False,
        "dry_run": dry_run,
        "client_name": "",
        "client_dir": "",
        "expediente": expediente,
        "contains": contains,
        "expediente_dir": "",
        "md_path": "",
        "backup_path": "",
        "error": "",
    }

    try:
        scan_root = Path(read_config_value(config_path, "scan_root"))

        context = json.loads(json_path.read_text(encoding="utf-8"))
        client_name = context.get("client_name") or ""
        payload["client_name"] = client_name

        if not client_name:
            payload["error"] = f"JSON sin client_name: {json_path}"
            print("ERROR:", payload["error"])
            emit_result(payload, json_result)
            return 1

        client_dir = find_client_dir(scan_root, client_name)
        if not client_dir:
            payload["error"] = f"No encuentro carpeta de cliente: {client_name}"
            print("ERROR:", payload["error"])
            emit_result(payload, json_result)
            return 1

        payload["client_dir"] = str(client_dir)

        expediente_dir = find_expediente_dir(
            client_dir=client_dir,
            expediente=expediente,
            contains=contains,
        )

        if not expediente_dir:
            payload["error"] = (
                f"No encuentro carpeta de expediente | cliente={client_name} "
                f"| expediente={expediente} | contains={contains}"
            )
            print("ERROR: no encuentro carpeta de expediente")
            print("Cliente:", client_name)
            print("Cliente dir:", client_dir)
            print("Expediente:", expediente)
            print("Contains:", contains)
            emit_result(payload, json_result)
            return 1

        payload["expediente_dir"] = str(expediente_dir)

        md_path = find_expediente_md(expediente_dir)
        payload["md_path"] = str(md_path)

        block = render_expediente_markdown(
            context=context,
            expediente=expediente,
            contains=contains,
        )

        if md_path.exists():
            existing = md_path.read_text(encoding="utf-8", errors="ignore")
        else:
            existing = initial_expediente_md(
                client_name=client_name,
                expediente=expediente,
                contains=contains,
                expediente_dir=expediente_dir,
            )

        new_text = replace_block(existing, block)
        changed = normalize_newlines(existing) != normalize_newlines(new_text)
        payload["changed"] = changed

        print("Cliente:", client_name)
        print("Cliente carpeta:", client_dir)
        print("Expediente carpeta:", expediente_dir)
        print("Markdown:", md_path)

        if dry_run:
            print("DRY RUN: habría cambios" if changed else "DRY RUN: sin cambios")
            print("")
            print(block)
            payload["ok"] = True
            emit_result(payload, json_result)
            return 0

        if not changed:
            print("SIN CAMBIOS: no escribo y no creo backup")
            payload["ok"] = True
            emit_result(payload, json_result)
            return 0

        if md_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = md_path.with_suffix(md_path.suffix + f".bak_index_{stamp}")
            shutil.copy2(md_path, backup)
            payload["backup_path"] = str(backup)
            print("Backup:", backup)

        md_path.write_text(new_text, encoding="utf-8")
        print("OK escrito:", md_path)

        payload["ok"] = True
        emit_result(payload, json_result)
        return 0

    except Exception as e:
        payload["error"] = repr(e)
        print("ERROR:", repr(e))
        emit_result(payload, json_result)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--expediente", required=True)
    parser.add_argument("--contains", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-result", action="store_true")
    args = parser.parse_args()

    return hydrate_one(
        config_path=Path(args.config),
        json_path=Path(args.json_path),
        expediente=args.expediente,
        contains=args.contains,
        dry_run=args.dry_run,
        json_result=args.json_result,
    )


if __name__ == "__main__":
    raise SystemExit(main())