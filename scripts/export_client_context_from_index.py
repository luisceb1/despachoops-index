from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
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


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\wáéíóúñü]+", "_", value, flags=re.IGNORECASE)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:120] or "sin_cliente"


def parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        return []
    return []


def top_items(counter: Counter, limit: int = 25) -> list[dict]:
    return [{"value": k, "count": v} for k, v in counter.most_common(limit)]


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--limit-clients", type=int, default=0)
    args = parser.parse_args()

    config_path = Path(args.config)
    data_dir = Path(read_config_value(config_path, "data_dir"))
    db = data_dir / "despacho_index.sqlite"

    output_dir = Path(args.output_dir) if args.output_dir else data_dir / "client_context_index"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("data_dir:", data_dir)
    print("db:", db)
    print("output_dir:", output_dir)

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row

    if not table_exists(con, "ocr_documents"):
        print("No existe tabla ocr_documents. Ejecuta primero enrich_ocr_documents.py")
        return 1

    rows = list(
        con.execute(
            """
            SELECT
                file_id,
                archivo_original,
                ruta_original,
                hash_documento,
                fecha_ocr,
                estado_ocr,
                status_ocr,
                cache_path,
                texto_chars,
                texto_truncado,
                confianza_aproximada,
                num_paginas,
                tipo_documento_detectado,
                posible_cliente,
                posible_expediente,
                fechas_detectadas_json,
                nifs_cifs_detectados_json,
                importes_detectados_json,
                plazos_detectados_json,
                procedimientos_detectados_json,
                updated_at
            FROM ocr_documents
            WHERE posible_cliente IS NOT NULL
              AND TRIM(posible_cliente) <> ''
            """
        )
    )

    by_client: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_client[row["posible_cliente"]].append(row)

    exported = 0
    index_rows = []

    for client_name, client_rows in sorted(by_client.items(), key=lambda x: x[0].lower()):
        if args.limit_clients and exported >= args.limit_clients:
            break

        type_counter = Counter()
        expediente_counter = Counter()
        nif_counter = Counter()
        amount_counter = Counter()
        date_counter = Counter()
        deadline_counter = Counter()
        procedure_counter = Counter()

        important_docs = []
        deadline_docs = []
        low_confidence_docs = []
        no_text_docs = []

        for r in client_rows:
            doc_type = r["tipo_documento_detectado"] or "otros"
            type_counter[doc_type] += 1

            exp = r["posible_expediente"] or ""
            if exp:
                expediente_counter[exp] += 1

            nifs = parse_json_list(r["nifs_cifs_detectados_json"])
            amounts = parse_json_list(r["importes_detectados_json"])
            dates = parse_json_list(r["fechas_detectadas_json"])
            deadlines = parse_json_list(r["plazos_detectados_json"])
            procedures = parse_json_list(r["procedimientos_detectados_json"])

            nif_counter.update(nifs)
            amount_counter.update(amounts)
            date_counter.update(dates)
            deadline_counter.update(deadlines)
            procedure_counter.update(procedures)

            base_doc = {
                "file_id": r["file_id"],
                "archivo": r["archivo_original"],
                "ruta": r["ruta_original"],
                "tipo": doc_type,
                "expediente": exp,
                "texto_chars": r["texto_chars"],
                "confianza_aproximada": r["confianza_aproximada"],
                "num_paginas": r["num_paginas"],
                "fechas": dates[:10],
                "nifs_cifs": nifs[:10],
                "importes": amounts[:10],
                "plazos": deadlines[:10],
                "procedimientos": procedures[:10],
            }

            if doc_type in {
                "notificacion_aeat",
                "notificacion_tgss",
                "notificacion_inss",
                "notificacion_sepe",
                "requerimiento",
                "diligencia",
                "sentencia",
                "auto_judicial",
                "decreto_judicial",
                "demanda",
                "contrato",
                "burofax",
            }:
                important_docs.append(base_doc)

            if deadlines:
                deadline_docs.append(base_doc)

            if not r["texto_chars"]:
                no_text_docs.append(base_doc)

            conf = r["confianza_aproximada"]
            if conf is not None and conf < 0.45:
                low_confidence_docs.append(base_doc)

        context = {
            "client_name": client_name,
            "client_key": slugify(client_name),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "DespachoOps Index / ocr_documents",
            "summary": {
                "ocr_documents": len(client_rows),
                "documents_with_text": sum(1 for r in client_rows if (r["texto_chars"] or 0) > 0),
                "documents_without_text": sum(1 for r in client_rows if not (r["texto_chars"] or 0)),
                "documents_with_deadlines": len(deadline_docs),
                "documents_low_confidence": len(low_confidence_docs),
                "expedientes_detectados": len(expediente_counter),
            },
            "document_types": top_items(type_counter, 30),
            "expedientes": top_items(expediente_counter, 40),
            "detected": {
                "nifs_cifs": top_items(nif_counter, 30),
                "importes": top_items(amount_counter, 30),
                "fechas": top_items(date_counter, 30),
                "plazos": top_items(deadline_counter, 30),
                "procedimientos": top_items(procedure_counter, 30),
            },
            "important_documents": important_docs[:100],
            "deadline_documents": deadline_docs[:100],
            "quality_warnings": {
                "no_text_documents": no_text_docs[:50],
                "low_confidence_documents": low_confidence_docs[:50],
            },
        }

        out_path = output_dir / f"{slugify(client_name)}.json"
        out_path.write_text(
            json.dumps(context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        index_rows.append(
            {
                "client_name": client_name,
                "client_key": slugify(client_name),
                "path": str(out_path),
                "ocr_documents": len(client_rows),
                "documents_with_deadlines": len(deadline_docs),
                "documents_low_confidence": len(low_confidence_docs),
            }
        )

        exported += 1

    index_path = output_dir / "_index.json"
    index_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "clients": index_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("OK")
    print("Clientes exportados:", exported)
    print("Index:", index_path)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())