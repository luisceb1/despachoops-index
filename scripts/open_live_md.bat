from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path


INDEX_MARKER = "## Contexto Index del expediente"
START = "<!-- DESPACHOOPS_EXPEDIENTE_INDEX_START -->"
END = "<!-- DESPACHOOPS_EXPEDIENTE_INDEX_END -->"


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


def parse_whitelist(path: Path) -> list[dict]:
    rows = []

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()

        if not raw:
            continue

        if raw.startswith("#"):
            continue

        parts = [p.strip() for p in raw.split("|")]

        if len(parts) < 2:
            rows.append(
                {
                    "line_no": line_no,
                    "json_path": "",
                    "expediente": "",
                    "contains": "",
                    "parse_error": "Formato inválido",
                }
            )
            continue

        rows.append(
            {
                "line_no": line_no,
                "json_path": parts[0],
                "expediente": parts[1],
                "contains": parts[2] if len(parts) >= 3 else "",
                "parse_error": "",
            }
        )

    return rows


def client_name_from_json_path(json_path: str) -> str:
    stem = Path(json_path).stem
    return " ".join(part.capitalize() for part in stem.replace("_", " ").split())


def find_client_dir(scan_root: Path, json_path: str) -> Path | None:
    stem = Path(json_path).stem
    target = normalize(stem.replace("_", " "))

    candidates: list[tuple[int, Path]] = []

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


def count_documents_from_md(text: str) -> str:
    m = re.search(r"- Documentos asociados:\s*(\d+)", text)
    return m.group(1) if m else ""


def count_deadlines_from_md(text: str) -> str:
    m = re.search(r"- Documentos con posibles plazos:\s*(\d+)", text)
    return m.group(1) if m else ""


def generated_at_from_md(text: str) -> str:
    m = re.search(r"_Generado automáticamente:\s*([^_]+)_", text)
    return m.group(1).strip() if m else ""


def latest_backup(md_path: Path) -> tuple[str, str]:
    backups = sorted(
        md_path.parent.glob(md_path.name + ".bak_index_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        return "", ""

    latest = backups[0]
    ts = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return str(latest), ts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--whitelist",
        default=r"D:\DespachoOpsData\Index\hydrate_expediente_whitelist.txt",
    )
    parser.add_argument(
        "--output",
        default=r"D:\DespachoOpsData\Index\live_expedientes_index.csv",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    scan_root = Path(read_config_value(config_path, "scan_root"))
    whitelist_path = Path(args.whitelist)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    whitelist_rows = parse_whitelist(whitelist_path)

    output_rows = []

    for row in whitelist_rows:
        line_no = row["line_no"]
        json_path = row["json_path"]
        expediente = row["expediente"]
        contains = row["contains"]

        base = {
            "line_no": line_no,
            "json_path": json_path,
            "cliente_estimado": client_name_from_json_path(json_path) if json_path else "",
            "cliente_carpeta": "",
            "expediente": expediente,
            "contains": contains,
            "expediente_carpeta": "",
            "md_path": "",
            "md_exists": "NO",
            "index_block_count": "",
            "start_marker_count": "",
            "end_marker_count": "",
            "documents_associated": "",
            "documents_with_deadlines": "",
            "generated_at": "",
            "latest_backup": "",
            "latest_backup_mtime": "",
            "status": "",
            "error": row.get("parse_error", ""),
        }

        if base["error"]:
            base["status"] = "ERROR"
            output_rows.append(base)
            continue

        client_dir = find_client_dir(scan_root, json_path)
        if not client_dir:
            base["status"] = "ERROR"
            base["error"] = "No se encuentra carpeta cliente"
            output_rows.append(base)
            continue

        base["cliente_carpeta"] = str(client_dir)

        expediente_dir = find_expediente_dir(client_dir, expediente, contains)
        if not expediente_dir:
            base["status"] = "ERROR"
            base["error"] = "No se encuentra carpeta expediente"
            output_rows.append(base)
            continue

        base["expediente_carpeta"] = str(expediente_dir)

        md_path = expediente_dir / "00_EXPEDIENTE.md"
        base["md_path"] = str(md_path)

        if not md_path.exists():
            base["status"] = "FALTA_MD"
            base["error"] = "No existe 00_EXPEDIENTE.md"
            output_rows.append(base)
            continue

        base["md_exists"] = "SI"

        text = md_path.read_text(encoding="utf-8", errors="replace")

        index_block_count = text.count(INDEX_MARKER)
        start_count = text.count(START)
        end_count = text.count(END)

        base["index_block_count"] = index_block_count
        base["start_marker_count"] = start_count
        base["end_marker_count"] = end_count
        base["documents_associated"] = count_documents_from_md(text)
        base["documents_with_deadlines"] = count_deadlines_from_md(text)
        base["generated_at"] = generated_at_from_md(text)

        backup, backup_ts = latest_backup(md_path)
        base["latest_backup"] = backup
        base["latest_backup_mtime"] = backup_ts

        if index_block_count == 1 and start_count == 1 and end_count == 1:
            base["status"] = "OK"
        else:
            base["status"] = "REVISAR"
            base["error"] = "Marcadores/bloques inesperados"

        output_rows.append(base)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "line_no",
                "status",
                "error",
                "cliente_estimado",
                "cliente_carpeta",
                "expediente",
                "contains",
                "expediente_carpeta",
                "md_path",
                "md_exists",
                "index_block_count",
                "start_marker_count",
                "end_marker_count",
                "documents_associated",
                "documents_with_deadlines",
                "generated_at",
                "latest_backup",
                "latest_backup_mtime",
                "json_path",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    counts = {}
    for row in output_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    print("Expedientes:", len(output_rows))
    print("Resumen:", counts)
    print("CSV:", output_path)

    for row in output_rows:
        if row["status"] != "OK":
            print("REVISAR:", row["status"], row["cliente_estimado"], row["expediente"], row["contains"], row["error"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())