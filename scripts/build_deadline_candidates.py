from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path


DEADLINE_TYPES = {
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
    "burofax",
    "modelo_tributario",
}


IMPORTANT_TYPES = {
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
    "burofax",
    "modelo_tributario",
}


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
def fix_mojibake(value):
    if not isinstance(value, str):
        return value

    if "Ã" in value or "Â" in value:
        try:
            return value.encode("latin1").decode("utf-8")
        except Exception:
            return value

    return value


def clean_output_row(row: dict) -> dict:
    return {key: fix_mojibake(value) for key, value in row.items()}


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


def get_all_docs(context: dict) -> list[dict]:
    docs = []

    for key in ("deadline_documents", "important_documents", "all_documents", "documents"):
        value = context.get(key)
        if isinstance(value, list):
            docs.extend(value)

    seen = set()
    deduped = []

    for doc in docs:
        ruta = doc.get("ruta") or ""
        archivo = doc.get("archivo") or ""
        key = ruta.lower() if ruta else archivo.lower()

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        deduped.append(doc)

    return deduped


def match_expediente(doc: dict, expediente: str, contains: str = "") -> bool:
    expediente_norm = normalize(expediente)
    contains_norm = normalize(contains)

    doc_exp = normalize(doc.get("expediente") or "")
    ruta = normalize(doc.get("ruta") or "")

    if expediente_norm:
        if expediente_norm not in doc_exp and expediente_norm not in ruta:
            return False

    if contains_norm:
        if contains_norm not in ruta and contains_norm not in doc_exp:
            return False

    return True


def first_value(values: list | None) -> str:
    if not values:
        return ""
    for value in values:
        value = str(value).strip()
        if value:
            return value
    return ""


def join_values(values: list | None, limit: int = 3) -> str:
    if not values:
        return ""

    cleaned = []
    seen = set()

    for value in values:
        value = str(value).strip()
        if not value:
            continue

        key = value.lower()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(value)

        if len(cleaned) >= limit:
            break

    return " | ".join(cleaned)


def candidate_score(doc: dict, plazo: str) -> int:
    score = 0
    tipo = doc.get("tipo") or ""

    if tipo in DEADLINE_TYPES:
        score += 50

    if tipo in IMPORTANT_TYPES:
        score += 20

    if doc.get("procedimientos"):
        score += 10

    if doc.get("fechas"):
        score += 10

    if doc.get("importes"):
        score += 5

    plazo_norm = normalize(plazo)

    if "habil" in plazo_norm:
        score += 15

    if "dias" in plazo_norm:
        score += 10

    if "mes" in plazo_norm:
        score += 8

    if "recurso" in plazo_norm:
        score += 10

    return score


def classify_risk(doc: dict, plazo: str) -> str:
    tipo = doc.get("tipo") or ""
    plazo_norm = normalize(plazo)

    if tipo in {
        "notificacion_aeat",
        "notificacion_tgss",
        "notificacion_inss",
        "notificacion_sepe",
        "requerimiento",
        "diligencia",
        "sentencia",
        "auto_judicial",
        "decreto_judicial",
    }:
        return "ALTO"

    if "10 dias" in plazo_norm or "15 dias" in plazo_norm or "habil" in plazo_norm:
        return "ALTO"

    if tipo in {"burofax", "demanda", "modelo_tributario"}:
        return "MEDIO"

    return "BAJO"


def build_candidates(whitelist_rows: list[dict]) -> list[dict]:
    out = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in whitelist_rows:
        json_path = row.get("json_path") or ""
        expediente = row.get("expediente") or ""
        contains = row.get("contains") or ""

        if row.get("parse_error"):
            out.append(
                {
                    "generated_at": now,
                    "status": "ERROR",
                    "estado_revision": "pendiente",
                    "riesgo": "",
                    "score": "",
                    "cliente": "",
                    "expediente": expediente,
                    "contains": contains,
                    "tipo": "",
                    "archivo": "",
                    "plazo_detectado": "",
                    "fechas_detectadas": "",
                    "procedimientos": "",
                    "importes": "",
                    "ruta": "",
                    "json_path": json_path,
                    "observaciones": row["parse_error"],
                }
            )
            continue

        try:
            context = json.loads(Path(json_path).read_text(encoding="utf-8"))
        except Exception as e:
            out.append(
                {
                    "generated_at": now,
                    "status": "ERROR",
                    "estado_revision": "pendiente",
                    "riesgo": "",
                    "score": "",
                    "cliente": "",
                    "expediente": expediente,
                    "contains": contains,
                    "tipo": "",
                    "archivo": "",
                    "plazo_detectado": "",
                    "fechas_detectadas": "",
                    "procedimientos": "",
                    "importes": "",
                    "ruta": "",
                    "json_path": json_path,
                    "observaciones": f"No se puede leer JSON: {e}",
                }
            )
            continue

        client_name = context.get("client_name") or Path(json_path).stem

        docs = [
            doc for doc in get_all_docs(context)
            if match_expediente(doc, expediente=expediente, contains=contains)
        ]

        seen_documents = set()

        for doc in docs:
            tipo = doc.get("tipo") or ""
            plazos = doc.get("plazos") or []

            if not plazos:
                continue

            if tipo not in DEADLINE_TYPES:
                continue

            archivo = doc.get("archivo") or ""
            ruta = doc.get("ruta") or ""

            dedupe_key = (
                normalize(client_name),
                normalize(expediente),
                normalize(contains),
                normalize(archivo),
                normalize(ruta),
            )

            if dedupe_key in seen_documents:
                continue

            seen_documents.add(dedupe_key)

            plazos_clean = []
            seen_plazos = set()

            for plazo in plazos:
                plazo = str(plazo).strip()
                if not plazo:
                    continue

                key = normalize(plazo)
                if key in seen_plazos:
                    continue

                seen_plazos.add(key)
                plazos_clean.append(plazo)

            if not plazos_clean:
                continue

            best_plazo = plazos_clean[0]
            best_score = max(candidate_score(doc, plazo) for plazo in plazos_clean)
            risk_order = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}
            best_risk = max(
                (classify_risk(doc, plazo) for plazo in plazos_clean),
                key=lambda r: risk_order.get(r, 0),
            )

            out.append(
                {
                    "generated_at": now,
                    "status": "OK",
                    "estado_revision": "pendiente",
                    "riesgo": best_risk,
                    "score": best_score,
                    "cliente": client_name,
                    "expediente": expediente,
                    "contains": contains,
                    "tipo": tipo,
                    "archivo": archivo,
                    "plazo_detectado": " | ".join(plazos_clean[:6]),
                    "fechas_detectadas": join_values(doc.get("fechas") or [], limit=4),
                    "procedimientos": join_values(doc.get("procedimientos") or [], limit=3),
                    "importes": join_values(doc.get("importes") or [], limit=3),
                    "ruta": ruta,
                    "json_path": json_path,
                    "observaciones": "",
                }
            )

    out.sort(
        key=lambda r: (
            {"ALTO": 3, "MEDIO": 2, "BAJO": 1}.get(r.get("riesgo", ""), 0),
            int(r["score"]) if str(r.get("score", "")).isdigit() else 0,
            r.get("cliente", ""),
            r.get("expediente", ""),
        ),
        reverse=True,
    )

    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--whitelist",
        default=r"D:\DespachoOpsData\Index\hydrate_expediente_whitelist.txt",
    )
    parser.add_argument(
        "--output",
        default=r"D:\DespachoOpsData\Index\deadline_candidates.csv",
    )
    args = parser.parse_args()

    whitelist_path = Path(args.whitelist)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = parse_whitelist(whitelist_path)
    candidates = [clean_output_row(row) for row in build_candidates(rows)]

    fieldnames = [
        "generated_at",
        "status",
        "estado_revision",
        "riesgo",
        "score",
        "cliente",
        "expediente",
        "contains",
        "tipo",
        "archivo",
        "plazo_detectado",
        "fechas_detectadas",
        "procedimientos",
        "importes",
        "ruta",
        "json_path",
        "observaciones",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        # Excel en configuración española suele abrir mejor CSV con separador ;
        f.write("sep=;\n")
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(candidates)

    counts = {}
    risk_counts = {}

    for row in candidates:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        risk = row.get("riesgo") or "SIN_RIESGO"
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

    print("Candidatos plazo:", len(candidates))
    print("Status:", counts)
    print("Riesgo:", risk_counts)
    print("CSV:", output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())