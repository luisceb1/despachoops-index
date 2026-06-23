from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

QUEUE_FIELDS = [
    "ruta", "hash_archivo", "extension", "tamano_bytes",
    "estado", "intentos", "ultimo_status", "cache_path", "actualizado",
]

PRIORITY_KEYWORDS = [
    "dni", "nie", "pasaporte",
    "aeat", "agencia tributaria", "hacienda",
    "seguridad social", "tgss", "inss", "sepe",
    "dehu", "notifica", "notificacion", "notificación",
    "requerimiento", "diligencia",
    "juzgado", "lexnet", "demanda", "sentencia", "decreto", "auto",
    "acta", "certificado", "contrato", "burofax",
    "factura", "modelo", "iva", "irpf", "renta",
    "nomina", "nómina",
]

def read_config_value(config_path: Path, key: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$")
    for line in config_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value.replace("\\\\", "\\")
    raise KeyError(f"No encuentro {key} en {config_path}")

def load_queue(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

def write_queue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in QUEUE_FIELDS})

def keyword_score(path: str) -> int:
    low = path.lower()
    return sum(1 for kw in PRIORITY_KEYWORDS if kw in low)

def priority(row: dict[str, str]) -> tuple:
    path = row.get("ruta", "")
    ext = row.get("extension", "").lower()
    estado = row.get("estado", "")
    status = row.get("ultimo_status", "").lower()

    try:
        size = int(row.get("tamano_bytes") or "0")
    except ValueError:
        size = 0

    mb = size / 1024 / 1024

    ext_rank = 0 if ext == ".pdf" else 10

    if estado == "pendiente":
        state_rank = 0
    elif estado == "error":
        state_rank = 3
    elif estado == "sin_texto":
        state_rank = 5
    else:
        state_rank = 20

    if mb <= 2:
        size_rank = 0
    elif mb <= 8:
        size_rank = 1
    elif mb <= 20:
        size_rank = 2
    elif mb <= 80:
        size_rank = 5
    else:
        size_rank = 20

    if "encrypted" in status or "cifrado" in status:
        error_rank = 50
    elif "poppler" in status or "pdfinfo" in status:
        error_rank = 30
    elif "timeout" in status:
        error_rank = 25
    else:
        error_rank = 0

    return (
        state_rank,
        ext_rank,
        size_rank,
        error_rank,
        -keyword_score(path),
        path.lower(),
    )

def candidate_rows_from_sqlite(db: Path, scan_root: Path, max_candidates: int = 5000) -> list[dict[str, str]]:
    con = sqlite3.connect(str(db))
    cur = con.cursor()

    sql = """
    SELECT f.path, f.extension, f.size_bytes, COALESCE(f.read_error, '') AS read_error
    FROM files f
    LEFT JOIN file_text t ON t.file_id = f.id
    WHERE lower(f.extension) = '.pdf'
      AND lower(f.path) LIKE lower(?)
      AND (
            COALESCE(t.text_full, '') = ''
         OR COALESCE(t.text_preview, '') = ''
         OR lower(COALESCE(f.read_error, '')) LIKE '%sin_texto%'
      )
    ORDER BY f.size_bytes ASC
    LIMIT ?
    """

    prefix = str(scan_root).rstrip("\\/") + "%"
    now = datetime.now().isoformat(timespec="seconds")

    out = []
    for path, ext, size, read_error in cur.execute(sql, (prefix, max_candidates)):
        out.append({
            "ruta": path,
            "hash_archivo": "",
            "extension": ext or ".pdf",
            "tamano_bytes": str(size or 0),
            "estado": "pendiente",
            "intentos": "0",
            "ultimo_status": read_error or "",
            "cache_path": "",
            "actualizado": now,
        })

    con.close()
    return out

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config_path = Path(args.config)
    scan_root = Path(read_config_value(config_path, "scan_root"))
    data_dir = Path(read_config_value(config_path, "data_dir"))
    db = data_dir / "despacho_index.sqlite"
    queue_path = data_dir / "ocr_jobs.csv"

    print("scan_root:", scan_root)
    print("data_dir:", data_dir)
    print("db:", db)
    print("queue:", queue_path)

    if not db.exists():
        raise SystemExit(f"No existe SQLite: {db}")

    existing = load_queue(queue_path)
    by_path = {r.get("ruta", ""): r for r in existing if r.get("ruta")}

    discovered = candidate_rows_from_sqlite(db, scan_root)

    added = 0
    for row in discovered:
        if row["ruta"] not in by_path:
            by_path[row["ruta"]] = row
            added += 1

    rows = list(by_path.values())
    rows.sort(key=priority)

    write_queue(queue_path, rows)

    pending_pdf = sum(
        1 for r in rows
        if r.get("estado") in {"pendiente", "error"} and r.get("extension") == ".pdf"
    )

    print("Filas cola:", len(rows))
    print("Añadidos desde SQLite:", added)
    print("PDF pendientes/error:", pending_pdf)

    print("\nTop 25 candidatos:")
    for r in rows[:25]:
        size_mb = int(r.get("tamano_bytes") or 0) / 1024 / 1024
        print(f"- {r.get('estado')} {r.get('extension')} {size_mb:.2f} MB :: {r.get('ruta')}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())