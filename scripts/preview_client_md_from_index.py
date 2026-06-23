from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


START = "<!-- DESPACHOOPS_INDEX_START -->"
END = "<!-- DESPACHOOPS_INDEX_END -->"

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
}

DEADLINE_RELEVANT_TYPES = {
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
    "autorizada",
    "autorizado",
    "autoridad",
    "autoridades",
    "automatizada",
    "nº factura",
    "num",
}


def amount_to_float(value: str) -> float | None:
    raw = value.lower().replace("€", "").replace("eur", "").replace("euros", "").strip()
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def clean_procedure_items(items: list[dict], limit: int = 12) -> list[dict]:
    out = []
    seen = set()

    for item in items:
        value = str(item.get("value", "")).strip()
        low = value.lower()

        if not value:
            continue

        if low in NOISY_PROCEDURE_WORDS:
            continue

        if any(noisy in low for noisy in NOISY_PROCEDURE_WORDS):
            continue

        if not re.search(
            r"(expediente|procedimiento|referencia|autos|nº|número|num\.?|erte|sancionador|concursal)",
            low,
        ):
            continue

        key = low
        if key in seen:
            continue

        seen.add(key)
        out.append(item)

        if len(out) >= limit:
            break

    return out


def bullet_items(
    items: list[dict],
    label_key: str = "value",
    count_key: str = "count",
    limit: int = 12,
) -> list[str]:
    out = []
    for item in items[:limit]:
        value = item.get(label_key, "")
        count = item.get(count_key, 0)
        if value:
            out.append(f"- {value}: {count}")
    return out


def doc_score(doc: dict) -> int:
    score = 0

    tipo = doc.get("tipo") or ""

    if tipo in IMPORTANT_TYPES:
        score += 10

    if doc.get("plazos"):
        score += 20

    if doc.get("procedimientos"):
        score += 8

    if doc.get("nifs_cifs"):
        score += 4

    if doc.get("importes"):
        score += 4

    if tipo in {"factura", "dni_nie", "nomina"}:
        score -= 8

    return score


def short_path(path: str, max_len: int = 145) -> str:
    if len(path) <= max_len:
        return path
    return "..." + path[-max_len:]


def doc_line(doc: dict) -> str:
    tipo = doc.get("tipo") or "documento"
    archivo = doc.get("archivo") or ""
    expediente = doc.get("expediente") or ""
    ruta = doc.get("ruta") or ""

    extras = []

    if expediente:
        extras.append(f"expediente: {expediente}")

    plazos = doc.get("plazos") or []
    if plazos:
        extras.append("plazos: " + "; ".join(plazos[:2]))

    procedimientos = doc.get("procedimientos") or []
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


def filter_deadline_docs(docs: list[dict], limit: int = 12) -> list[dict]:
    filtered = []

    for doc in docs:
        tipo = doc.get("tipo") or ""
        archivo = (doc.get("archivo") or "").lower()
        ruta = (doc.get("ruta") or "").lower()

        if tipo not in DEADLINE_RELEVANT_TYPES:
            continue

        if not doc.get("plazos"):
            continue

        # Evitar falsos positivos de documentación ordinaria.
        if "vida laboral" in archivo:
            continue

        if "datos fiscales" in archivo:
            continue

        if "irpf" in ruta and "requerimiento" not in ruta and "notific" not in ruta:
            continue

        filtered.append(doc)

    filtered.sort(key=doc_score, reverse=True)
    return filtered[:limit]


def filter_important_docs(docs: list[dict], limit: int = 18) -> list[dict]:
    filtered = []

    for doc in docs:
        tipo = doc.get("tipo") or ""
        expediente = (doc.get("expediente") or "").lower()
        archivo = (doc.get("archivo") or "").lower()
        ruta = (doc.get("ruta") or "").lower()

        if tipo not in IMPORTANT_TYPES:
            continue

        # Ruido documental ordinario: se queda en Index, no en 00_CLIENTE.md.
        if tipo in {"factura", "dni_nie", "nomina"}:
            continue

        # Contratos laborales rutinarios.
        if tipo == "contrato":
            is_labor_contract = (
                "contratos trabajo" in ruta
                or "contratos de trabajo" in ruta
                or "contrato trabajo" in archivo
                or expediente in {"contratos", "contratos trabajo", "contratos de trabajo"}
            )

            # Mantener contratos de local/arrendamiento/cervecería/operación concreta.
            is_relevant_contract = (
                "local" in ruta
                or "arrend" in archivo
                or "arrend" in ruta
                or "cerveceria" in archivo
                or "cervecería" in archivo
                or "compraventa" in archivo
                or "urbacsadi" in archivo
            )

            if is_labor_contract and not is_relevant_contract:
                continue

        if "datos fiscales" in archivo:
            continue

        if "vida laboral" in archivo:
            continue

        if "irpf" in ruta and "requerimiento" not in ruta and "notific" not in ruta:
            continue

        filtered.append(doc)

    filtered.sort(key=doc_score, reverse=True)
    return filtered[:limit]


def dedupe_docs_by_filename(docs: list[dict], limit: int = 5) -> list[dict]:
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


def render_markdown(context: dict) -> str:
    summary = context.get("summary", {})
    detected = context.get("detected", {})
    quality = context.get("quality_warnings", {})

    lines: list[str] = []
    lines.append(START)
    lines.append("")
    lines.append("## Contexto Index")
    lines.append("")
    lines.append(f"_Generado automáticamente: {context.get('generated_at', '')}_")
    lines.append("")

    lines.append("### Resumen documental")
    lines.append("")
    lines.append(f"- Documentos OCR asociados: {summary.get('ocr_documents', 0)}")
    lines.append(f"- Documentos con texto: {summary.get('documents_with_text', 0)}")
    lines.append(f"- Documentos sin texto: {summary.get('documents_without_text', 0)}")
    lines.append(f"- Documentos con posibles plazos: {summary.get('documents_with_deadlines', 0)}")
    lines.append(f"- Expedientes/carpetas detectadas: {summary.get('expedientes_detectados', 0)}")
    lines.append("")

    lines.append("### Tipos documentales principales")
    lines.append("")
    type_lines = bullet_items(context.get("document_types", []), limit=12)
    lines.extend(type_lines if type_lines else ["- Sin datos."])
    lines.append("")

    lines.append("### Carpetas/expedientes principales")
    lines.append("")
    exp_lines = bullet_items(context.get("expedientes", []), limit=10)
    lines.extend(exp_lines if exp_lines else ["- Sin datos."])
    lines.append("")

    lines.append("### Datos detectados")
    lines.append("")

    nifs = bullet_items(detected.get("nifs_cifs", []), limit=10)
    fechas = bullet_items(detected.get("fechas", []), limit=10)
    plazos = bullet_items(detected.get("plazos", []), limit=10)
    procedimientos = bullet_items(
        clean_procedure_items(detected.get("procedimientos", []), limit=10),
        limit=10,
    )

    lines.append("**NIF/CIF más frecuentes**")
    lines.extend(nifs if nifs else ["- Sin datos."])
    lines.append("")

    lines.append("**Fechas frecuentes o recientes**")
    lines.extend(fechas if fechas else ["- Sin datos."])
    lines.append("")

    lines.append("**Plazos detectados**")
    lines.extend(plazos if plazos else ["- Sin plazos detectados."])
    lines.append("")

    lines.append("**Procedimientos / referencias**")
    lines.extend(procedimientos if procedimientos else ["- Sin referencias limpias detectadas."])
    lines.append("")

    deadline_docs = filter_deadline_docs(context.get("deadline_documents", []), limit=5)
    deadline_docs = dedupe_docs_by_filename(deadline_docs, limit=5)
    deadline_doc_paths = {doc.get("ruta") for doc in deadline_docs}

    lines.append("### Documentos con posibles plazos jurídicos/administrativos")
    lines.append("")
    if deadline_docs:
        for doc in deadline_docs:
            lines.append(doc_line(doc))
    else:
        lines.append("- Sin documentos con plazo jurídico/administrativo claro.")
    lines.append("")

    important_docs = filter_important_docs(context.get("important_documents", []), limit=30)
    important_docs = [
        doc for doc in important_docs
        if doc.get("ruta") not in deadline_doc_paths
    ]
    important_docs = dedupe_docs_by_filename(important_docs, limit=5)

    lines.append("### Documentos relevantes sugeridos")
    lines.append("")
    if important_docs:
        for doc in important_docs:
            lines.append(doc_line(doc))
    else:
        lines.append("- Sin documentos relevantes sugeridos.")
    lines.append("")

    low_conf = quality.get("low_confidence_documents", [])
    no_text = quality.get("no_text_documents", [])

    lines.append("### Alertas de calidad")
    lines.append("")
    if no_text:
        lines.append(f"- Documentos sin texto detectados: {len(no_text)}")
    else:
        lines.append("- No constan documentos sin texto en este contexto.")

# La confianza OCR aproximada todavía está en calibración.
# No se muestra en 00_CLIENTE.md para evitar falsos positivos masivos.

    lines.append("")
    lines.append(END)
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    context = json.loads(json_path.read_text(encoding="utf-8"))

    md = render_markdown(context)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print("Preview Markdown:", out)
    else:
        print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())