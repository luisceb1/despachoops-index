from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path


TEXT_LIMIT = 50_000

NIF_CIF_RE = re.compile(
    r"\b(?:[XYZ]\d{7}[A-Z]|[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]|\d{8}[A-Z])\b",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b(?:"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{1,2}\s+de\s+"
    r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+de\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(
    r"\b\d{1,3}(?:\.\d{3})*(?:,\d{2})\s*(?:€|eur|euros)?\b|\b\d+,\d{2}\s*(?:€|eur|euros)?\b",
    re.IGNORECASE,
)

PROCEDURE_RE = re.compile(
    r"\b(?:autos?|procedimiento|expediente|referencia|n[úu]mero|nº|num\.?)\s*[:\-]?\s*"
    r"[A-Z0-9][A-Z0-9/\-\.]{3,}\b",
    re.IGNORECASE,
)

DEADLINE_PATTERNS = [
    re.compile(r"\bplazo\s+de\s+\d+\s+d[ií]as\b", re.IGNORECASE),
    re.compile(r"\ben\s+el\s+plazo\s+de\s+\d+\s+d[ií]as\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+d[ií]as\s+h[aá]biles\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+d[ií]as\s+naturales\b", re.IGNORECASE),
    re.compile(r"\bhasta\s+el\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE),
]

TYPE_RULES = [
    ("notificacion_aeat", ["agencia tributaria", "aeat", "sede electrónica de la agencia estatal"]),
    ("notificacion_tgss", ["tesorería general de la seguridad social", "tgss"]),
    ("notificacion_inss", ["instituto nacional de la seguridad social", "inss"]),
    ("notificacion_sepe", ["servicio público de empleo estatal", "sepe"]),
    ("requerimiento", ["requerimiento", "se requiere", "requerirle"]),
    ("diligencia", ["diligencia", "diligencia de ordenación"]),
    ("sentencia", ["sentencia", "fallo", "magistrado-juez"]),
    ("auto_judicial", [" auto ", "parte dispositiva", "antecedentes de hecho", "fundamentos de derecho"]),
    ("decreto_judicial", ["decreto", "letrado de la administración de justicia"]),
    ("demanda", ["demanda", "suplico al juzgado", "hechos", "fundamentos de derecho"]),
    ("factura", ["factura", "base imponible", "iva", "total factura"]),
    ("nomina", ["nómina", "nomina", "salario base", "líquido a percibir"]),
    ("contrato", ["contrato", "arrendador", "arrendatario", "cláusula"]),
    ("burofax", ["burofax", "acuse de recibo", "certificación de contenido"]),
    ("certificado", ["certificado", "certifica", "certifico"]),
    ("dni_nie", ["documento nacional de identidad", "dni", "nie", "pasaporte"]),
    ("modelo_tributario", ["modelo 100", "modelo 130", "modelo 303", "modelo 390", "modelo 111", "modelo 115", "modelo 200"]),
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

        quoted = (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        )
        if quoted:
            value = value[1:-1]

        return value.replace("\\\\", "\\")

    raise KeyError(f"No encuentro {key} en {config_path}")


def load_ocr_jobs(queue_path: Path) -> dict[str, dict[str, str]]:
    if not queue_path.exists():
        return {}
    with queue_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {r.get("ruta", ""): r for r in rows if r.get("ruta")}


def init_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS ocr_documents (
            file_id INTEGER PRIMARY KEY,
            archivo_original TEXT,
            ruta_original TEXT,
            hash_documento TEXT,
            fecha_ocr TEXT,
            motor_ocr TEXT,
            idioma_ocr TEXT,
            estado_ocr TEXT,
            status_ocr TEXT,
            cache_path TEXT,
            texto_extraido TEXT,
            texto_chars INTEGER,
            texto_truncado INTEGER,
            confianza_aproximada REAL,
            num_paginas INTEGER,
            tipo_documento_detectado TEXT,
            posible_cliente TEXT,
            posible_expediente TEXT,
            fechas_detectadas_json TEXT,
            nifs_cifs_detectados_json TEXT,
            importes_detectados_json TEXT,
            plazos_detectados_json TEXT,
            procedimientos_detectados_json TEXT,
            updated_at TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
        """
    )


def parse_pages(status: str) -> int | None:
    m = re.search(r"paginas=(\d+)", status or "", re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def clean_items(items: list[str], limit: int = 30) -> list[str]:
    seen = set()
    out = []
    for item in items:
        value = " ".join(str(item).strip().split())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def detect_deadlines(text: str) -> list[str]:
    found = []
    for pat in DEADLINE_PATTERNS:
        found.extend(pat.findall(text))
    return clean_items(found, limit=30)


def detect_type(text: str, path: str) -> str:
    low = f"{path}\n{text[:8000]}".lower()
    scores: list[tuple[int, str]] = []
    for doc_type, needles in TYPE_RULES:
        score = sum(1 for needle in needles if needle in low)
        if score:
            scores.append((score, doc_type))
    if not scores:
        return "otros"
    scores.sort(reverse=True)
    return scores[0][1]


def infer_client(scan_root: Path, path: str) -> str:
    try:
        rel = Path(path).relative_to(scan_root)
        parts = rel.parts
        return parts[0] if parts else ""
    except Exception:
        marker = "\\Clientes\\"
        if marker.lower() in path.lower():
            after = re.split(re.escape(marker), path, flags=re.IGNORECASE, maxsplit=1)[1]
            return after.split("\\")[0]
        return ""


def infer_expediente(scan_root: Path, path: str) -> str:
    try:
        rel = Path(path).relative_to(scan_root)
        parts = rel.parts
    except Exception:
        marker = "\\Clientes\\"
        if marker.lower() in path.lower():
            after = re.split(re.escape(marker), path, flags=re.IGNORECASE, maxsplit=1)[1]
            parts = tuple(after.split("\\"))
        else:
            return ""

    # Cliente = parts[0]. El expediente probable suele ser una carpeta intermedia.
    if len(parts) >= 3:
        return parts[1]
    return ""


def approximate_confidence(text: str, status: str) -> float:
    if not text.strip():
        return 0.0
    if "OCR_OK" not in (status or ""):
        return 0.35

    chars = len(text)
    alnum = sum(ch.isalnum() for ch in text)
    weird = sum(1 for ch in text if ord(ch) > 127 and ch not in "áéíóúÁÉÍÓÚñÑüÜ€ºª")
    ratio = alnum / max(chars, 1)

    score = 0.55
    if chars > 500:
        score += 0.15
    if chars > 1500:
        score += 0.10
    if ratio > 0.55:
        score += 0.10
    if weird / max(chars, 1) > 0.03:
        score -= 0.15

    return round(max(0.0, min(score, 0.95)), 2)


def read_text_from_cache_or_index(cache_path: str, text_preview: str | None, text_full: str | None) -> str:
    if cache_path:
        p = Path(cache_path)
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="ignore")
    return text_full or text_preview or ""


def enrich_one(scan_root: Path, row: sqlite3.Row, job: dict[str, str]) -> dict:
    path = row["path"]
    status = job.get("ultimo_status", "") or row["read_error"] or ""
    cache_path = job.get("cache_path", "") or ""

    text = read_text_from_cache_or_index(cache_path, row["text_preview"], row["text_full"])
    text = text.strip()

    truncated = 1 if len(text) > TEXT_LIMIT else 0
    stored_text = text[:TEXT_LIMIT]

    fechas = clean_items(DATE_RE.findall(text), limit=50)
    nifs = clean_items([x.upper() for x in NIF_CIF_RE.findall(text)], limit=50)
    importes = clean_items(AMOUNT_RE.findall(text), limit=50)
    plazos = detect_deadlines(text)
    procedimientos = clean_items(PROCEDURE_RE.findall(text), limit=30)

    now = datetime.now().isoformat(timespec="seconds")

    return {
        "file_id": row["id"],
        "archivo_original": row["name"],
        "ruta_original": path,
        "hash_documento": job.get("hash_archivo", "") or "",
        "fecha_ocr": job.get("actualizado", "") or now,
        "motor_ocr": "tesseract",
        "idioma_ocr": "spa+eng",
        "estado_ocr": job.get("estado", "") or ("index_text" if text else "sin_texto"),
        "status_ocr": status,
        "cache_path": cache_path,
        "texto_extraido": stored_text,
        "texto_chars": len(text),
        "texto_truncado": truncated,
        "confianza_aproximada": approximate_confidence(text, status),
        "num_paginas": parse_pages(status),
        "tipo_documento_detectado": detect_type(text, path),
        "posible_cliente": infer_client(scan_root, path),
        "posible_expediente": infer_expediente(scan_root, path),
        "fechas_detectadas_json": json.dumps(fechas, ensure_ascii=False),
        "nifs_cifs_detectados_json": json.dumps(nifs, ensure_ascii=False),
        "importes_detectados_json": json.dumps(importes, ensure_ascii=False),
        "plazos_detectados_json": json.dumps(plazos, ensure_ascii=False),
        "procedimientos_detectados_json": json.dumps(procedimientos, ensure_ascii=False),
        "updated_at": now,
    }


def upsert(con: sqlite3.Connection, data: dict) -> None:
    con.execute(
        """
        INSERT INTO ocr_documents (
            file_id, archivo_original, ruta_original, hash_documento, fecha_ocr,
            motor_ocr, idioma_ocr, estado_ocr, status_ocr, cache_path,
            texto_extraido, texto_chars, texto_truncado, confianza_aproximada,
            num_paginas, tipo_documento_detectado, posible_cliente,
            posible_expediente, fechas_detectadas_json, nifs_cifs_detectados_json,
            importes_detectados_json, plazos_detectados_json,
            procedimientos_detectados_json, updated_at
        ) VALUES (
            :file_id, :archivo_original, :ruta_original, :hash_documento, :fecha_ocr,
            :motor_ocr, :idioma_ocr, :estado_ocr, :status_ocr, :cache_path,
            :texto_extraido, :texto_chars, :texto_truncado, :confianza_aproximada,
            :num_paginas, :tipo_documento_detectado, :posible_cliente,
            :posible_expediente, :fechas_detectadas_json, :nifs_cifs_detectados_json,
            :importes_detectados_json, :plazos_detectados_json,
            :procedimientos_detectados_json, :updated_at
        )
        ON CONFLICT(file_id) DO UPDATE SET
            archivo_original=excluded.archivo_original,
            ruta_original=excluded.ruta_original,
            hash_documento=excluded.hash_documento,
            fecha_ocr=excluded.fecha_ocr,
            motor_ocr=excluded.motor_ocr,
            idioma_ocr=excluded.idioma_ocr,
            estado_ocr=excluded.estado_ocr,
            status_ocr=excluded.status_ocr,
            cache_path=excluded.cache_path,
            texto_extraido=excluded.texto_extraido,
            texto_chars=excluded.texto_chars,
            texto_truncado=excluded.texto_truncado,
            confianza_aproximada=excluded.confianza_aproximada,
            num_paginas=excluded.num_paginas,
            tipo_documento_detectado=excluded.tipo_documento_detectado,
            posible_cliente=excluded.posible_cliente,
            posible_expediente=excluded.posible_expediente,
            fechas_detectadas_json=excluded.fechas_detectadas_json,
            nifs_cifs_detectados_json=excluded.nifs_cifs_detectados_json,
            importes_detectados_json=excluded.importes_detectados_json,
            plazos_detectados_json=excluded.plazos_detectados_json,
            procedimientos_detectados_json=excluded.procedimientos_detectados_json,
            updated_at=excluded.updated_at
        """,
        data,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--limit", type=int, default=0)
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

    jobs = load_ocr_jobs(queue_path)

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    init_schema(con)

    sql = """
    SELECT
        f.id, f.path, f.name, f.extension, f.size_bytes, f.read_error,
        t.text_preview, t.text_full
    FROM files f
    LEFT JOIN file_text t ON t.file_id = f.id
    WHERE lower(f.extension) = '.pdf'
      AND lower(f.path) LIKE lower(?)
      AND (
            f.path IN ({placeholders})
         OR COALESCE(t.text_preview, '') <> ''
         OR COALESCE(t.text_full, '') <> ''
      )
    """

    job_paths = list(jobs.keys())
    if not job_paths:
        print("No hay ocr_jobs.csv o está vacío")
        return 0

    prefix = str(scan_root).rstrip("\\/") + "%"
    placeholders = ",".join("?" for _ in job_paths)

    sql = sql.format(placeholders=placeholders)
    params = [prefix] + job_paths

    processed = 0
    with_text = 0
    with_nif = 0
    with_amount = 0
    with_deadline = 0

    for row in con.execute(sql, params):
        job = jobs.get(row["path"], {})
        data = enrich_one(scan_root, row, job)
        upsert(con, data)
        processed += 1

        if data["texto_chars"] > 0:
            with_text += 1
        if json.loads(data["nifs_cifs_detectados_json"]):
            with_nif += 1
        if json.loads(data["importes_detectados_json"]):
            with_amount += 1
        if json.loads(data["plazos_detectados_json"]):
            with_deadline += 1

        if args.limit and processed >= args.limit:
            break

        if processed % 500 == 0:
            print("Procesados:", processed)

    con.commit()

    print("")
    print("OK")
    print("OCR docs enriquecidos:", processed)
    print("Con texto:", with_text)
    print("Con NIF/CIF:", with_nif)
    print("Con importes:", with_amount)
    print("Con plazos:", with_deadline)

    print("")
    print("Tipos detectados:")
    for tipo, n in con.execute(
        """
        SELECT tipo_documento_detectado, COUNT(*)
        FROM ocr_documents
        GROUP BY tipo_documento_detectado
        ORDER BY COUNT(*) DESC
        LIMIT 20
        """
    ):
        print(tipo, n)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())