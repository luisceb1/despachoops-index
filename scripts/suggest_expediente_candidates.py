from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


RELEVANT_TYPES = {
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


NOISY_CLIENT_NAMES = {
    "IRPF",
    "AEAT",
    "Cuentas Anuales",
    "SEGURIDAD SOCIAL",
}


NOISY_EXPEDIENTES = {
    "",
    ".",
    "irpf",
    "aeat",
    "cuentas anuales",
    "seguridad social",
    "contratos",
    "contratos trabajo",
    "contratos de trabajo",
    "contratos y hojas de horas",
    "01. bbdd personal",
    "bbdd personal",
    "facturas",
    "facturas 2022",
    "facturas 2023",
    "facturas 2024",
    "facturas 2025",
    "facturas 2026",
    "dni",
    "nóminas",
    "nominas",
    "documentacion",
    "documentación",
    "documentacion asesoria",
    "documentación asesoría",
    "escrituras y documentos",
    "excels",
    "excel",
    "documentacion coches",
    "documentación coches",
    "modelos 2024",
    "modelos 2025",
    "modelos 2026",
    "2023",
    "2024",
    "2025",
    "2026",
}


NOISY_PATH_PARTS = {
    "contratos trabajo",
    "contratos de trabajo",
    "contratos y hojas de horas",
    "bbdd personal",
    "facturas",
    "nominas",
    "nóminas",
    "dni",
    "excels",
    "documentacion asesoria",
    "documentación asesoría",
    "modelos 2025",
    "cuentas anuales",
}


GOOD_KEYWORDS = {
    "aeat": 25,
    "tgss": 22,
    "sepe": 20,
    "inss": 20,
    "juzgado": 25,
    "judicial": 25,
    "demanda": 25,
    "sancion": 22,
    "sanción": 22,
    "sancionador": 22,
    "requerimiento": 24,
    "embargo": 22,
    "recurso": 18,
    "tear": 25,
    "inspeccion": 22,
    "inspección": 22,
    "subvencion": 16,
    "subvención": 16,
    "extranjeria": 16,
    "extranjería": 16,
    "contencioso": 24,
    "administrativo": 14,
    "responsabilidad patrimonial": 22,
    "despido": 22,
    "conciliacion": 16,
    "conciliación": 16,
    "fogasa": 20,
    "monitorio": 18,
    "diligencia": 18,
    "sentencia": 22,
}


def normalize(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("ñ", "n")
    value = re.sub(r"[^\w]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def short_path(path: str, max_len: int = 180) -> str:
    if len(path) <= max_len:
        return path
    return "..." + path[-max_len:]


def get_all_docs(context: dict) -> list[dict]:
    docs = []

    for key in ("deadline_documents", "important_documents", "all_documents", "documents"):
        value = context.get(key)
        if isinstance(value, list):
            docs.extend(value)

    seen = set()
    out = []

    for doc in docs:
        ruta = doc.get("ruta") or ""
        archivo = doc.get("archivo") or ""
        key = ruta.lower() if ruta else archivo.lower()

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        out.append(doc)

    return out


def expediente_key_from_doc(doc: dict) -> str:
    expediente = (doc.get("expediente") or "").strip()
    if expediente:
        return expediente

    ruta = doc.get("ruta") or ""
    parts = re.split(r"[\\/]+", ruta)

    if len(parts) >= 2:
        return parts[-2]

    return ""


def is_transversal_client(client_name: str) -> bool:
    client_norm = normalize(client_name)
    return client_norm in {normalize(x) for x in NOISY_CLIENT_NAMES}


def has_good_keyword(text: str) -> bool:
    text_norm = normalize(text)

    for keyword in GOOD_KEYWORDS:
        if normalize(keyword) in text_norm:
            return True

    return False


def is_noisy_expediente(expediente: str, ruta_sample: str = "") -> bool:
    exp_norm = normalize(expediente)
    ruta_norm = normalize(ruta_sample)

    if exp_norm in {normalize(x) for x in NOISY_EXPEDIENTES}:
        return True

    for part in NOISY_PATH_PARTS:
        part_norm = normalize(part)

        if part_norm in ruta_norm:
            # Si dentro de esa ruta hay señales administrativas/judiciales fuertes,
            # permitimos el expediente. Ej.: Contratos trabajo/Mohcine/Embargo AEAT.
            if has_good_keyword(ruta_norm):
                return False
            return True

    return False


def score_group(docs: list[dict], expediente: str, ruta_sample: str) -> int:
    score = 0

    types = Counter(doc.get("tipo") or "otros" for doc in docs)
    deadline_count = sum(1 for doc in docs if doc.get("plazos"))
    relevant_count = sum(1 for doc in docs if (doc.get("tipo") or "") in RELEVANT_TYPES)

    score += deadline_count * 30
    score += relevant_count * 12
    score += len(docs)

    exp_norm = normalize(expediente)
    ruta_norm = normalize(ruta_sample)
    haystack = f"{exp_norm} {ruta_norm}"

    for keyword, value in GOOD_KEYWORDS.items():
        if normalize(keyword) in haystack:
            score += value

    if is_noisy_expediente(expediente, ruta_sample):
        score -= 150

    if types.get("factura", 0) > relevant_count:
        score -= 30

    if types.get("dni_nie", 0) > relevant_count:
        score -= 30

    if types.get("nomina", 0) > relevant_count:
        score -= 25

    if types.get("contrato", 0) > relevant_count and not has_good_keyword(haystack):
        score -= 40

    return score


def infer_contains(expediente: str, ruta_sample: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", ruta_sample) if p]
    exp_norm = normalize(expediente)

    strong = (
        "liquidacion",
        "liquidación",
        "requerimiento",
        "expediente",
        "sancion",
        "sanción",
        "tear",
        "embargo",
        "demanda",
        "inspeccion",
        "inspección",
        "recurso",
        "contencioso",
        "monitorio",
        "subvencion",
        "subvención",
    )

    for part in reversed(parts[:-1]):
        part_norm = normalize(part)

        if part_norm == exp_norm:
            continue

        if any(normalize(s) in part_norm for s in strong):
            return part

    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contexts-dir",
        default=r"D:\DespachoOpsData\Index\client_context_index",
    )
    parser.add_argument(
        "--output",
        default=r"D:\DespachoOpsData\Index\expediente_candidates.csv",
    )
    parser.add_argument("--min-score", type=int, default=150)
    parser.add_argument("--min-docs", type=int, default=2)
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    contexts_dir = Path(args.contexts_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    for json_path in sorted(contexts_dir.glob("*.json")):
        if json_path.name == "_index.json":
            continue

        try:
            context = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            print("ERROR leyendo:", json_path, e)
            continue

        client_name = context.get("client_name") or json_path.stem

        if is_transversal_client(client_name):
            continue

        docs = get_all_docs(context)
        groups = defaultdict(list)

        for doc in docs:
            expediente = expediente_key_from_doc(doc)
            groups[expediente].append(doc)

        for expediente, group_docs in groups.items():
            if len(group_docs) < args.min_docs:
                continue

            ruta_sample = ""
            for doc in group_docs:
                ruta_sample = doc.get("ruta") or ""
                if ruta_sample:
                    break

            score = score_group(group_docs, expediente, ruta_sample)

            if score < args.min_score:
                continue

            type_counter = Counter(doc.get("tipo") or "otros" for doc in group_docs)
            deadline_count = sum(1 for doc in group_docs if doc.get("plazos"))
            relevant_count = sum(
                1 for doc in group_docs if (doc.get("tipo") or "") in RELEVANT_TYPES
            )

            contains = infer_contains(expediente, ruta_sample)

            rows.append(
                {
                    "score": score,
                    "client_name": client_name,
                    "expediente": expediente,
                    "contains_sugerido": contains,
                    "documents": len(group_docs),
                    "documents_with_deadlines": deadline_count,
                    "relevant_documents": relevant_count,
                    "top_types": "; ".join(
                        f"{k}:{v}" for k, v in type_counter.most_common(5)
                    ),
                    "json_path": str(json_path),
                    "ruta_sample": short_path(ruta_sample),
                    "whitelist_line": f"{json_path}|{expediente}|{contains}",
                }
            )

    rows.sort(
        key=lambda r: (
            int(r["score"]),
            int(r["documents_with_deadlines"]),
            int(r["documents"]),
        ),
        reverse=True,
    )

    rows = rows[: args.limit]

    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "score",
                "client_name",
                "expediente",
                "contains_sugerido",
                "documents",
                "documents_with_deadlines",
                "relevant_documents",
                "top_types",
                "json_path",
                "ruta_sample",
                "whitelist_line",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("Candidatos:", len(rows))
    print("CSV:", output)
    print("")

    for row in rows[:30]:
        print(
            row["score"],
            row["documents_with_deadlines"],
            row["documents"],
            row["client_name"],
            "|",
            row["expediente"],
            "|",
            row["contains_sugerido"],
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())