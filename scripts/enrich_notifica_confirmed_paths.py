from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


DEFAULT_CONFIRMED_CSV = r"\\Luiscp\d\DespachoOpsData\Index\notifica_assignments_confirmed.csv"
DEFAULT_OUT_XLSX = r"\\Luiscp\d\DespachoOpsData\Index\notifica_assignments_confirmed.xlsx"

CLIENT_FOLDER_KEYS = {
    "cliente_carpeta",
    "client_folder",
    "folder_path",
    "path",
    "root_path",
}

AUTO_EXISTING_NOTE = "Destino propuesto automaticamente; pendiente de revision humana."
AUTO_MISSING_NOTE = "Carpeta Notificaciones no existe; pendiente de crear/confirmar."
NO_CLIENT_FOLDER_NOTE = "No se pudo inferir carpeta cliente."


def strip_sep_line(lines: list[str]) -> list[str]:
    if lines and lines[0].strip().lower() == "sep=;":
        return lines[1:]
    return lines


def detect_delimiter(lines: list[str]) -> str:
    data_lines = strip_sep_line(lines)
    sample = "\n".join(data_lines[:20])

    if sample:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            if dialect.delimiter in {";", ",", "\t"}:
                return dialect.delimiter
        except csv.Error:
            pass

    header = data_lines[0] if data_lines else ""
    comma_count = header.count(",")
    semicolon_count = header.count(";")
    tab_count = header.count("\t")

    if tab_count > comma_count and tab_count > semicolon_count:
        return "\t"
    if comma_count > semicolon_count:
        return ","
    if semicolon_count > comma_count:
        return ";"
    return ";"


def read_csv_flexible(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise last_error or UnicodeDecodeError("utf-8", b"", 0, 1, "unknown error")

    raw_lines = text.splitlines()
    lines = strip_sep_line(raw_lines)
    delimiter = detect_delimiter(raw_lines)
    reader = csv.DictReader(lines, delimiter=delimiter)
    fieldnames = [field.strip() for field in (reader.fieldnames or [])]
    rows = [
        {(key or "").strip(): (value or "").strip() for key, value in row.items()}
        for row in reader
    ]
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        f.write("sep=;\n")
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fieldnames} for row in rows)


def write_xlsx(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Confirmaciones"
    sheet.append(fieldnames)

    for row in rows:
        sheet.append([row.get(field, "") for field in fieldnames])

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font

    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(fieldnames))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    for column_idx, field in enumerate(fieldnames, start=1):
        values = [field, *(str(row.get(field, "")) for row in rows[:200])]
        width = min(max(len(value) for value in values) + 2, 70)
        sheet.column_dimensions[get_column_letter(column_idx)].width = width

    workbook.save(path)


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def walk_json_values(value: object) -> Iterable[object]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json_values(child)


def candidate_path(value: object) -> Path | None:
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if "\\Clientes\\" not in text and "/Clientes/" not in text:
        return None

    return Path(text)


def client_folder_from_path(path: Path) -> Path | None:
    parts = path.parts
    lower_parts = [part.lower() for part in parts]
    if "clientes" not in lower_parts:
        return None

    idx = lower_parts.index("clientes")
    if idx + 1 >= len(parts):
        return None

    return Path(*parts[: idx + 2])


def find_obvious_folder(data: object) -> Path | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if normalize_key(str(key)) not in CLIENT_FOLDER_KEYS:
                continue
            path = candidate_path(value)
            if not path:
                continue
            folder = client_folder_from_path(path)
            if folder:
                return folder if folder.exists() else path

        for value in data.values():
            found = find_obvious_folder(value)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_obvious_folder(value)
            if found:
                return found

    return None


def infer_client_folder_from_json(json_path: Path) -> Path | None:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

    obvious = find_obvious_folder(data)
    if obvious:
        return obvious

    for value in walk_json_values(data):
        path = candidate_path(value)
        if not path:
            continue
        folder = client_folder_from_path(path)
        if folder:
            return folder

    return None


def append_observation(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    if note in existing:
        return existing
    if not existing:
        return note
    return existing + " | " + note


def should_process(row: dict[str, str], force: bool) -> bool:
    if (row.get("confirmado") or "").strip().upper() == "SI":
        return False
    if row.get("estado_asignacion") != "cliente_identificado":
        return False
    if not row.get("client_context_json"):
        return False
    if row.get("confirmed_expediente_path") and not force:
        return False
    return True


def enrich_rows(rows: list[dict[str, str]], force: bool) -> dict[str, int]:
    counts = {
        "existing": 0,
        "missing": 0,
        "none": 0,
        "human": 0,
    }

    for row in rows:
        if (row.get("confirmado") or "").strip().upper() == "SI":
            counts["human"] += 1
            continue

        if row.get("confirmed_expediente_path") and not force:
            counts["human"] += 1
            continue

        if not should_process(row, force):
            continue

        client_folder = infer_client_folder_from_json(Path(row["client_context_json"]))
        if not client_folder:
            row["accion"] = "elegir_expediente"
            row["observaciones"] = append_observation(row.get("observaciones", ""), NO_CLIENT_FOLDER_NOTE)
            counts["none"] += 1
            continue

        target = client_folder / "Notificaciones"
        row["confirmed_expediente_path"] = str(target)
        row["confirmado"] = "NO"

        if target.exists():
            row["accion"] = "confirmar_archivo"
            row["observaciones"] = append_observation(row.get("observaciones", ""), AUTO_EXISTING_NOTE)
            counts["existing"] += 1
        else:
            row["accion"] = "crear_carpeta_y_confirmar"
            row["observaciones"] = append_observation(row.get("observaciones", ""), AUTO_MISSING_NOTE)
            counts["missing"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propone confirmed_expediente_path en la plantilla de confirmaciones Notifica."
    )
    parser.add_argument("--confirmed-csv", default=DEFAULT_CONFIRMED_CSV)
    parser.add_argument("--out-xlsx", default=DEFAULT_OUT_XLSX)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    confirmed_csv = Path(args.confirmed_csv)
    out_xlsx = Path(args.out_xlsx)

    fieldnames, rows = read_csv_flexible(confirmed_csv)
    counts = enrich_rows(rows, force=args.force)

    write_csv(confirmed_csv, fieldnames, rows)
    write_xlsx(out_xlsx, fieldnames, rows)

    print("Filas leidas:", len(rows))
    print("Destinos propuestos existentes:", counts["existing"])
    print("Destinos propuestos no existentes:", counts["missing"])
    print("Sin destino:", counts["none"])
    print("Confirmaciones humanas conservadas:", counts["human"])
    print("CSV:", confirmed_csv)
    print("XLSX:", out_xlsx)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
