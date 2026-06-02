from pathlib import Path

from openpyxl import load_workbook

from despachoops_index.config import IndexOptions, LONG_PATH_THRESHOLD
from despachoops_index.dashboard import build_dashboard
from despachoops_index.indexer import build_index


def test_dashboard_sheets_and_duplicates(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    payload = b"%PDF-1.4 minimal"
    (root / "mismo.pdf").write_bytes(payload)
    dup_dir = root / "cliente"
    dup_dir.mkdir()
    (dup_dir / "mismo.pdf").write_bytes(payload)
    long_dir = root / "expediente"
    long_dir.mkdir()
    long_name = "a" * 200 + ".txt"
    (long_dir / long_name).write_text("x", encoding="utf-8")

    db = tmp_path / "index.sqlite"
    build_index(IndexOptions(root=root, db_path=db, include_text=False))

    out = tmp_path / "reports" / "dash.xlsx"
    result = build_dashboard(db, out)
    assert out.exists()
    assert "Duplicados_Probables" in result.sheets

    wb = load_workbook(out, read_only=True)
    assert "Resumen" in wb.sheetnames
    assert "Rutas_Largas" in wb.sheetnames
    assert "Archivos_Temporales_Ignorados" in wb.sheetnames

    dup_ws = wb["Duplicados_Probables"]
    dup_rows = list(dup_ws.iter_rows(min_row=2, values_only=True))
    assert any(row and row[0] == "mismo.pdf" for row in dup_rows)

    long_ws = wb["Rutas_Largas"]
    long_rows = list(long_ws.iter_rows(min_row=2, values_only=True))
    assert any(int(row[1]) >= LONG_PATH_THRESHOLD for row in long_rows if row[1])
    wb.close()
