from __future__ import annotations

import argparse
import csv
import html
import zipfile
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


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig")

    lines = text.splitlines()
    if lines and lines[0].strip().lower() == "sep=;":
        text = "\n".join(lines[1:])

    reader = csv.reader(text.splitlines(), delimiter=";")
    rows = list(reader)

    if not rows:
        return [], []

    rows = [[fix_mojibake(cell) for cell in row] for row in rows]

    return rows[0], rows[1:]


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


def sheet_xml(headers: list[str], rows: list[list[str]]) -> str:
    all_rows = [headers] + rows
    xml_rows = []

    for r_idx, row in enumerate(all_rows, start=1):
        cells = []
        for c_idx, value in enumerate(row):
            cells.append(cell_xml(r_idx, c_idx, value))
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

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
    <autoFilter ref="A1:{col_name(len(headers)-1)}{max(1, len(rows)+1)}"/>
</worksheet>
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


def workbook_xml(sheet_name: str) -> str:
    sheet_name = html.escape(sheet_name)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>
    </sheets>
</workbook>
'''


def workbook_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
'''


def root_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
'''


def content_types_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
'''


def write_xlsx(headers: list[str], rows: list[list[str]], output_path: Path, sheet_name: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("xl/workbook.xml", workbook_xml(sheet_name))
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        z.writestr("xl/styles.xml", styles_xml())
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml(headers, rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sheet-name", default="Plazos")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    headers, rows = read_csv(input_path)
    write_xlsx(headers, rows, output_path, args.sheet_name)

    print("Filas:", len(rows))
    print("XLSX:", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())