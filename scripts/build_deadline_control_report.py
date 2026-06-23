from __future__ import annotations

import argparse
import csv
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape


def fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value

    if "Ã" in value or "Â" in value:
        try:
            return value.encode("latin1").decode("utf-8")
        except Exception:
            return value

    return value


def read_semicolon_csv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")

    lines = text.splitlines()
    if lines and lines[0].strip().lower() == "sep=;":
        text = "\n".join(lines[1:])

    reader = csv.DictReader(text.splitlines(), delimiter=";")
    return [
        {k: fix_mojibake(v) for k, v in row.items()}
        for row in reader
    ]


def parse_date(value) -> date | None:
    if value is None:
        return None

    # Si viene como número de serie Excel: 46189 -> 2026-06-16 aprox.
    if isinstance(value, (int, float)):
        try:
            return date(1899, 12, 30) + timedelta(days=int(value))
        except Exception:
            return None

    value = str(value).strip()

    if not value:
        return None

    # Si viene como texto numérico: "46189"
    if value.isdigit():
        try:
            return date(1899, 12, 30) + timedelta(days=int(value))
        except Exception:
            pass

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    return None


def classify(row: dict, today: date) -> str:
    estado = (row.get("estado_plazo") or "").strip().lower()
    vencimiento = parse_date(row.get("fecha_vencimiento") or "")

    if estado in {"hecho", "cerrado", "finalizado"}:
        return "hechos"

    if not vencimiento:
        return "sin_fecha"

    if vencimiento < today:
        return "vencidos"

    return "pendientes"


def col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def cell_xml(row_idx: int, col_idx: int, value: str) -> str:
    ref = f"{col_name(col_idx)}{row_idx}"
    value = "" if value is None else str(value)
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def worksheet_xml(headers: list[str], rows: list[dict]) -> str:
    all_rows = [headers]
    for row in rows:
        all_rows.append([row.get(h, "") for h in headers])

    xml_rows = []
    for r_idx, row_values in enumerate(all_rows, start=1):
        cells = [cell_xml(r_idx, c_idx, value) for c_idx, value in enumerate(row_values)]
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    last_col = col_name(max(0, len(headers) - 1))
    last_row = max(1, len(all_rows))

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheetViews>
        <sheetView workbookViewId="0">
            <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
        </sheetView>
    </sheetViews>
    <sheetData>
        {"".join(xml_rows)}
    </sheetData>
    <autoFilter ref="A1:{last_col}{last_row}"/>
</worksheet>
'''


def workbook_xml(sheet_names: list[str]) -> str:
    sheets = []
    for idx, name in enumerate(sheet_names, start=1):
        sheets.append(f'<sheet name="{escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        {"".join(sheets)}
    </sheets>
</workbook>
'''


def workbook_rels_xml(sheet_count: int) -> str:
    rels = []
    for idx in range(1, sheet_count + 1):
        rels.append(
            f'<Relationship Id="rId{idx}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )

    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        f'Target="styles.xml"/>'
    )

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    {"".join(rels)}
</Relationships>
'''


def root_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
'''


def styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
    <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
    <borders count="1"><border/></borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
    <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
'''


def content_types_xml(sheet_count: int) -> str:
    sheets = []
    for idx in range(1, sheet_count + 1):
        sheets.append(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    {"".join(sheets)}
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
'''


def write_xlsx(output_path: Path, sheets: dict[str, list[dict]], headers: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_names = list(sheets.keys())

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml(len(sheet_names)))
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("xl/workbook.xml", workbook_xml(sheet_names))
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheet_names)))
        z.writestr("xl/styles.xml", styles_xml())

        for idx, name in enumerate(sheet_names, start=1):
            z.writestr(f"xl/worksheets/sheet{idx}.xml", worksheet_xml(headers, sheets[name]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=r"D:\DespachoOpsData\Index\confirmed_deadlines.csv",
    )
    parser.add_argument(
        "--output",
        default=r"D:\DespachoOpsData\Index\deadline_control_report.xlsx",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = read_semicolon_csv(input_path)
    today = date.today()

    headers = [
        "estado",
        "estado_plazo",
        "cliente",
        "expediente",
        "contains",
        "riesgo",
        "tipo",
        "archivo",
        "plazo_detectado",
        "fecha_notificacion",
        "fecha_vencimiento",
        "actuacion",
        "responsable",
        "fechas_detectadas",
        "procedimientos",
        "importes",
        "ruta",
        "observaciones",
        "calendar_event_id",
    ]

    buckets = {
        "pendientes": [],
        "sin_fecha": [],
        "vencidos": [],
        "hechos": [],
        "todos": rows,
    }

    for row in rows:
        bucket = classify(row, today)
        buckets[bucket].append(row)

    write_xlsx(output_path, buckets, headers)

    print("Plazos confirmados:", len(rows))
    print("Pendientes:", len(buckets["pendientes"]))
    print("Sin fecha:", len(buckets["sin_fecha"]))
    print("Vencidos:", len(buckets["vencidos"]))
    print("Hechos:", len(buckets["hechos"]))
    print("XLSX:", output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())