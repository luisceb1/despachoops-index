from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


START = "<!-- DESPACHOOPS_EXPEDIENTE_INDEX_START -->"
END = "<!-- DESPACHOOPS_EXPEDIENTE_INDEX_END -->"


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
    "contrato",
    "burofax",
    "modelo_tributario",
    "certificado",
}


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


NOISY_PROCEDURE_WORDS = {
    "autorizado",
    "autorizada",
    "autoridad",
    "autoridades",
    "procedimiento general",
    "procedimiento administrativo",
    "procedimiento establecido",
    "expediente para",
    "nº certificado",
    "n certificado",
    "certificado",
    "autoliquidacion",
    "autoliquidaciones",
}


def normalize(value: str) -> str:
    value = (value or "").lower()
    value = value.replace("ñ", "n")
    value = re.sub(r"[^\w]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def amount_to_float(value: str) -> float | None:
    raw = value.lower().replace("€", "").replace("eur", "").replace("euros", "").strip()
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def short_path(path: str, max_len: int = 145) -> str:
    if len(path) <= max_len:
        return path
    return "..." + path[-max_len:]


def doc_score(doc: dict) -> int:
    score = 0

    tipo = doc.get("tipo") or ""

    if tipo in IMPORTANT_TYPES:
        score += 10

    if doc.get("plazos"):
        score += 30

    if doc.get("procedimientos"):
        score += 8

    if doc.get("importes"):
        score += 5

    if doc.get("fechas"):
        score += 3

    if tipo in {"factura", "dni_nie", "nomina"}:
        score -= 10

    return score


def clean_procedure_value(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def is_clean_procedure(value: str) -> bool:
    value = clean_procedure_value(value)
    low = value.lower()

    if not value:
        return False

    if low in NOISY_PROCEDURE_WORDS:
        return False

    if any(low == noisy for noisy in NOISY_PROCEDURE_WORDS):
        return False

    return bool(
        re.search(
            r"(expediente|procedimiento|referencia|autos|nº|número|num\.?|sancionador|tear|reclamaci[oó]n|diligencia|registro|liquidaci[oó]n|recurso)",
            low,
        )
    )


def doc_line(doc: dict) -> str:
    tipo = doc.get("tipo") or "documento"
    archivo = doc.get("archivo") or ""
    ruta = doc.get("ruta") or ""

    extras = []

    plazos = doc.get("plazos") or []
    if plazos:
        extras.append("plazos: " + "; ".join(plazos[:2]))

    procedimientos = []
    for value in doc.get("procedimientos") or []:
        value = clean_procedure_value(value)
        if is_clean_procedure(value):
            procedimientos.append(value)

    if procedimientos:
        extras.append("ref.: " + "; ".join(procedimientos[:2]))

    importes = doc.get("importes") or []
    relevant_amounts = []
    for amount in importes:
        parsed = amount_to_float(str(amount))
        if parsed is not None and parsed >= 50:
            relevant_amounts.append(amount)

    if relevant_amounts:
        extras.append("importes: " + "; ".join(relevant_amounts[:2]))

    fechas = doc.get("fechas") or []
    if fechas:
        extras.append("fechas: " + "; ".join(fechas[:2]))

    suffix = f" — {' | '.join(extras)}" if extras else ""
    return f"- **{tipo}** — `{archivo}`{suffix}\n  - Ruta: `{short_path(ruta)}`"


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


def top_items(counter: Counter, limit: int = 10) -> list[str]:
    out = []
    for value, count in counter.most_common(limit):
        if value:
            out.append(f"- {value}: {count}")
    return out


def dedupe_docs_by_filename(docs: list[dict], limit: int = 8) -> list[dict]:
    seen = set()
    out = []

    for doc in docs:
        key = (doc.get("archivo") or "").strip().lower()
        if not key:
            key = (doc.get("ruta") or "").strip().lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(doc)

        if len(out) >= limit:
            break

    return out


def render_expediente_markdown(
    context: dict,
    expediente: str,
    contains: str = "",
    limit_docs: int = 8,
) -> str:
    client_name = context.get("client_name") or ""

    docs = [
        doc for doc in get_all_docs(context)
        if match_expediente(doc, expediente=expediente, contains=contains)
    ]

    docs.sort(key=doc_score, reverse=True)

    type_counter = Counter(doc.get("tipo") or "otros" for doc in docs)

    deadline_docs = [
        doc for doc in docs
        if doc.get("plazos") and (doc.get("tipo") or "") in DEADLINE_TYPES
    ]
    deadline_docs.sort(key=doc_score, reverse=True)
    deadline_docs = dedupe_docs_by_filename(deadline_docs, limit=limit_docs)

    deadline_paths = {doc.get("ruta") for doc in deadline_docs}

    important_docs = [
        doc for doc in docs
        if (doc.get("tipo") or "") in IMPORTANT_TYPES
        and doc.get("ruta") not in deadline_paths
    ]
    important_docs.sort(key=doc_score, reverse=True)
    important_docs = dedupe_docs_by_filename(important_docs, limit=limit_docs)

    nifs = Counter()
    fechas = Counter()
    plazos = Counter()
    procedimientos = Counter()
    importes = Counter()

    for doc in docs:
        for value in doc.get("nifs_cifs") or []:
            value = str(value).strip()
            if value:
                nifs[value] += 1

        for value in doc.get("fechas") or []:
            value = str(value).strip()
            if value:
                fechas[value] += 1

        for value in doc.get("plazos") or []:
            value = str(value).strip()
            if value:
                plazos[value] += 1

        for value in doc.get("procedimientos") or []:
            value = clean_procedure_value(value)
            if is_clean_procedure(value):
                procedimientos[value] += 1

        for value in doc.get("importes") or []:
            value = str(value).strip()
            parsed = amount_to_float(value)
            if parsed is not None and parsed >= 50:
                importes[value] += 1

    title = expediente
    if contains:
        title = f"{expediente} / {contains}"

    lines: list[str] = []
    lines.append(START)
    lines.append("")
    lines.append("## Contexto Index del expediente")
    lines.append("")
    lines.append(f"_Generado automáticamente: {context.get('generated_at', '')}_")
    lines.append("")

    lines.append("### Resumen")
    lines.append("")
    lines.append(f"- Cliente: {client_name}")
    lines.append(f"- Expediente/carpeta: {title}")
    lines.append(f"- Documentos asociados: {len(docs)}")
    lines.append(f"- Documentos con posibles plazos: {len(deadline_docs)}")
    lines.append("")

    lines.append("### Tipos documentales")
    lines.append("")
    type_lines = top_items(type_counter, limit=8)
    lines.extend(type_lines if type_lines else ["- Sin datos."])
    lines.append("")

    lines.append("### Documentos con posibles plazos")
    lines.append("")
    if deadline_docs:
        for doc in deadline_docs:
            lines.append(doc_line(doc))
    else:
        lines.append("- Sin documentos con plazo claro en este expediente.")
    lines.append("")

    lines.append("### Documentos relevantes")
    lines.append("")
    if important_docs:
        for doc in important_docs:
            lines.append(doc_line(doc))
    else:
        lines.append("- Sin documentos relevantes sugeridos.")
    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Datos detectados por Index</summary>")
    lines.append("")

    lines.append("### Datos detectados en el expediente")
    lines.append("")

    lines.append("**NIF/CIF frecuentes**")
    nifs_lines = top_items(nifs, limit=8)
    lines.extend(nifs_lines if nifs_lines else ["- Sin datos."])
    lines.append("")

    lines.append("**Fechas frecuentes**")
    fechas_lines = top_items(fechas, limit=8)
    lines.extend(fechas_lines if fechas_lines else ["- Sin datos."])
    lines.append("")

    lines.append("**Plazos detectados**")
    plazos_lines = top_items(plazos, limit=8)
    lines.extend(plazos_lines if plazos_lines else ["- Sin plazos detectados."])
    lines.append("")

    lines.append("**Referencias / procedimientos**")
    procedimientos_lines = top_items(procedimientos, limit=8)
    lines.extend(procedimientos_lines if procedimientos_lines else ["- Sin referencias detectadas."])
    lines.append("")

    lines.append("**Importes relevantes**")
    importes_lines = top_items(importes, limit=8)
    lines.extend(importes_lines if importes_lines else ["- Sin importes relevantes detectados."])
    lines.append("")

    lines.append("</details>")
    lines.append("")
    lines.append(END)
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--expediente", required=True)
    parser.add_argument("--contains", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--limit-docs", type=int, default=8)
    args = parser.parse_args()

    json_path = Path(args.json_path)
    context = json.loads(json_path.read_text(encoding="utf-8"))

    md = render_expediente_markdown(
        context=context,
        expediente=args.expediente,
        contains=args.contains,
        limit_docs=args.limit_docs,
    )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print("Preview expediente:", out)
    else:
        print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())