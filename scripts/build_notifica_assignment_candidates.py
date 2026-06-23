from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


DEFAULT_NOTIFICA_INBOX = r"C:\DespachoOpsData\Notifica\notificaciones_inbox.csv"
DEFAULT_LIVE_EXPEDIENTES = r"D:\DespachoOpsData\Index\live_expedientes_index.csv"
DEFAULT_OUT_CSV = r"D:\DespachoOpsData\Index\notifica_assignment_candidates.csv"
DEFAULT_OUT_XLSX = r"D:\DespachoOpsData\Index\notifica_assignment_candidates.xlsx"

OUTPUT_FIELDS = [
    "notification_id",
    "source",
    "received_at",
    "entity_nif",
    "entity_name",
    "title",
    "download_status",
    "main_pdf_path",
    "receipt_path",
    "cliente_sugerido",
    "expediente_sugerido",
    "expediente_path",
    "match_score",
    "match_reason",
    "estado_asignacion",
    "accion_sugerida",
    "observaciones",
]

STOPWORDS = {
    "para",
    "por",
    "con",
    "sin",
    "del",
    "las",
    "los",
    "una",
    "uno",
    "unos",
    "unas",
    "este",
    "esta",
    "estos",
    "estas",
    "notificacion",
    "comunicacion",
    "procedimiento",
    "expediente",
    "administracion",
    "electronica",
}


@dataclass(frozen=True)
class Match:
    row: dict[str, str] | None
    score: int
    reasons: list[str]


def fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value

    if "\u00c3" in value or "\u00c2" in value:
        try:
            return value.encode("latin1").decode("utf-8")
        except Exception:
            return value

    return value


def clean_row(row: dict[str, str]) -> dict[str, str]:
    return {
        (key or "").strip(): fix_mojibake(value or "").strip()
        for key, value in row.items()
    }


def read_semicolon_csv(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise last_error or UnicodeDecodeError("utf-8", b"", 0, 1, "unknown error")

    lines = text.splitlines()
    if lines and lines[0].strip().lower() == "sep=;":
        text = "\n".join(lines[1:])

    reader = csv.DictReader(text.splitlines(), delimiter=";")
    return [clean_row(row) for row in reader]


def normalize(value: str) -> str:
    value = fix_mojibake(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_nif(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def first_present(row: dict[str, str], aliases: Iterable[str]) -> str:
    normalized_keys = {normalize(key): key for key in row}

    for alias in aliases:
        key = normalized_keys.get(normalize(alias))
        if key and row.get(key):
            return row[key].strip()

    return ""


def values_by_terms(row: dict[str, str], terms: Iterable[str]) -> list[str]:
    term_norms = [normalize(term) for term in terms]
    values: list[str] = []

    for key, value in row.items():
        key_norm = normalize(key)
        if any(term and term in key_norm for term in term_norms):
            if value:
                values.append(value)

    return values


def unique_join(values: Iterable[str], separator: str = " | ") -> str:
    cleaned = []
    seen = set()

    for value in values:
        value = (value or "").strip()
        key = normalize(value)
        if not value or key in seen:
            continue
        seen.add(key)
        cleaned.append(value)

    return separator.join(cleaned)


def relevant_tokens(*values: str) -> set[str]:
    tokens: set[str] = set()

    for value in values:
        for token in normalize(value).split():
            if token in STOPWORDS:
                continue
            if len(token) >= 4 or token.isdigit() and len(token) >= 3:
                tokens.add(token)

    return tokens


def notification_value(row: dict[str, str], canonical: str) -> str:
    aliases = {
        "notification_id": ("notification_id", "id", "notificacion_id", "notificacion_id"),
        "source": ("source", "origen", "buzon", "buzon"),
        "received_at": ("received_at", "fecha_recepcion", "fecha_recepcion", "received"),
        "entity_nif": ("entity_nif", "nif", "cif", "dni", "destinatario_nif"),
        "entity_name": ("entity_name", "entity", "cliente", "razon_social", "razon_social", "destinatario"),
        "title": ("title", "titulo", "titulo", "asunto", "subject"),
        "download_status": ("download_status", "estado_descarga", "status"),
        "main_pdf_path": ("main_pdf_path", "pdf_path", "document_path", "documento_path"),
        "receipt_path": ("receipt_path", "acuse_path", "justificante_path"),
    }
    return first_present(row, aliases[canonical])


def index_cliente(row: dict[str, str]) -> str:
    return first_present(
        row,
        (
            "cliente_sugerido",
            "cliente",
            "cliente_nombre",
            "cliente_estimado",
            "cliente_carpeta",
            "nombre_cliente",
        ),
    )


def index_expediente(row: dict[str, str]) -> str:
    return first_present(
        row,
        ("expediente_sugerido", "expediente", "expediente_nombre", "contains", "nombre"),
    )


def index_path(row: dict[str, str]) -> str:
    return first_present(
        row,
        ("expediente_path", "expediente_carpeta", "ruta", "path", "md_path", "cliente_carpeta"),
    )


def index_nifs(row: dict[str, str]) -> set[str]:
    values = values_by_terms(row, ("nif", "cif", "dni"))
    return {nif for value in values for nif in [normalize_nif(value)] if nif}


def score_against_index(notification: dict[str, str], index_row: dict[str, str]) -> Match:
    score = 0
    reasons: list[str] = []

    notif_nif = normalize_nif(notification_value(notification, "entity_nif"))
    if notif_nif and notif_nif in index_nifs(index_row):
        score += 70
        reasons.append("NIF exacto")

    notif_client_values = [
        notification_value(notification, "entity_name"),
        first_present(notification, ("cliente_sugerido", "cliente", "cliente_detectado")),
    ]
    index_client_values = [
        index_cliente(index_row),
        *values_by_terms(index_row, ("cliente", "razon", "razon")),
    ]

    notif_clients = [normalize(value) for value in notif_client_values if normalize(value)]
    index_clients = [normalize(value) for value in index_client_values if normalize(value)]

    exact_client = any(left == right for left in notif_clients for right in index_clients)
    partial_client = any(
        left in right or right in left
        for left in notif_clients
        for right in index_clients
        if len(left) >= 4 and len(right) >= 4
    )

    if exact_client:
        score += 50
        reasons.append("cliente exacto/normalizado")
    elif partial_client:
        score += 30
        reasons.append("cliente parcial")

    notif_tokens = relevant_tokens(
        notification_value(notification, "title"),
        first_present(notification, ("procedure", "procedimiento", "numero_procedimiento")),
        first_present(notification, ("sender", "remitente", "organismo")),
    )
    index_text = " ".join(
        [
            index_expediente(index_row),
            index_path(index_row),
            unique_join(values_by_terms(index_row, ("expediente", "nombre", "ruta", "path"))),
        ]
    )
    index_tokens = relevant_tokens(index_text)
    token_hits = sorted(notif_tokens & index_tokens)

    if token_hits:
        score += 20
        reasons.append("tokens en expediente/ruta: " + ", ".join(token_hits[:8]))

    return Match(row=index_row, score=min(score, 100), reasons=reasons)


def best_match(notification: dict[str, str], index_rows: list[dict[str, str]]) -> Match:
    best = Match(row=None, score=0, reasons=[])

    for index_row in index_rows:
        current = score_against_index(notification, index_row)
        if current.score > best.score:
            best = current

    return best


def build_output_rows(
    notifications: list[dict[str, str]],
    index_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []

    for notification in notifications:
        match = best_match(notification, index_rows)
        matched = match.row if match.row and match.score > 0 else None
        estado = "pendiente_confirmacion" if match.score >= 50 else "requiere_revision"
        accion = (
            "revisar_y_confirmar_destino"
            if match.score >= 50
            else "revisar_manualmente"
        )

        output_rows.append(
            {
                "notification_id": notification_value(notification, "notification_id"),
                "source": notification_value(notification, "source"),
                "received_at": notification_value(notification, "received_at"),
                "entity_nif": notification_value(notification, "entity_nif"),
                "entity_name": notification_value(notification, "entity_name"),
                "title": notification_value(notification, "title"),
                "download_status": notification_value(notification, "download_status"),
                "main_pdf_path": notification_value(notification, "main_pdf_path"),
                "receipt_path": notification_value(notification, "receipt_path"),
                "cliente_sugerido": index_cliente(matched) if matched else "",
                "expediente_sugerido": index_expediente(matched) if matched else "",
                "expediente_path": index_path(matched) if matched else "",
                "match_score": str(match.score),
                "match_reason": " | ".join(match.reasons),
                "estado_asignacion": estado,
                "accion_sugerida": accion,
                "observaciones": "" if match.score >= 50 else "Sin match >=50 en indice vivo",
            }
        )

    return output_rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        f.write("sep=;\n")
        writer = csv.DictWriter(
            f,
            fieldnames=OUTPUT_FIELDS,
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Asignaciones"
    sheet.append(OUTPUT_FIELDS)

    for row in rows:
        sheet.append([row.get(field, "") for field in OUTPUT_FIELDS])

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font

    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(OUTPUT_FIELDS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"

    for column_idx, field in enumerate(OUTPUT_FIELDS, start=1):
        values = [field, *(str(row.get(field, "")) for row in rows[:200])]
        width = min(max(len(value) for value in values) + 2, 60)
        sheet.column_dimensions[get_column_letter(column_idx)].width = width

    workbook.save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Propone asignacion cliente/expediente para la bandeja exportada de Notifica."
    )
    parser.add_argument("--notifica-inbox", default=DEFAULT_NOTIFICA_INBOX)
    parser.add_argument("--live-expedientes", default=DEFAULT_LIVE_EXPEDIENTES)
    parser.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    parser.add_argument("--out-xlsx", default=DEFAULT_OUT_XLSX)
    args = parser.parse_args()

    notifica_inbox = Path(args.notifica_inbox)
    live_expedientes = Path(args.live_expedientes)
    out_csv = Path(args.out_csv)
    out_xlsx = Path(args.out_xlsx)

    notifications = read_semicolon_csv(notifica_inbox)
    index_rows = read_semicolon_csv(live_expedientes)
    output_rows = build_output_rows(notifications, index_rows)

    write_csv(output_rows, out_csv)
    write_xlsx(output_rows, out_xlsx)

    counts: dict[str, int] = {}
    for row in output_rows:
        estado = row["estado_asignacion"]
        counts[estado] = counts.get(estado, 0) + 1

    print("Notificaciones:", len(output_rows))
    print("Resumen:", counts)
    print("CSV:", out_csv)
    print("XLSX:", out_xlsx)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


