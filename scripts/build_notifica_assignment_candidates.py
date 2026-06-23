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
    "index_columns_detected",
    "match_debug",
]

STOP_TOKENS = {
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027",
    "2028",
    "2029",
    "2030",
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
    "administrativa",
    "electronica",
    "aceptar",
    "rechazar",
    "fecha",
    "caducidad",
    "si",
    "no",
    "pendiente",
    "comparecencia",
    "agencia",
    "estatal",
    "tesoreria",
    "general",
    "seguridad",
    "social",
    "aeat",
    "tributaria",
    "notificar",
    "notificaciones",
    "genericas",
    "administrati",
    "ayuntamiento",
    "organismo",
    "postal",
    "pago",
    "pagos",
    "devoluciones",
}

COMPANY_FORM_TOKENS = {
    "sl",
    "sll",
    "slu",
    "sa",
    "sau",
    "sociedad",
    "limitada",
    "anonima",
}

INDEX_COLUMN_ALIASES = {
    "cliente": (
        "cliente",
        "client",
        "nombre_cliente",
        "cliente_nombre",
        "display_name",
        "nombre",
        "cliente_estimado",
        "cliente_carpeta",
    ),
    "expediente": (
        "expediente",
        "expediente_nombre",
        "nombre_expediente",
        "asunto",
        "contains",
    ),
    "ruta": (
        "path",
        "expediente_path",
        "ruta",
        "folder",
        "folder_path",
        "expediente_carpeta",
        "md_path",
    ),
    "nif": (
        "nif",
        "dni",
        "cif",
        "nie",
        "tax_id",
        "cliente_nif",
    ),
}

NOTIFICATION_ALIASES = {
    "notification_id": ("notification_id", "id", "notificacion_id"),
    "source": ("source", "origen", "buzon"),
    "received_at": ("received_at", "fecha_recepcion", "received"),
    "entity_nif": ("entity_nif", "nif", "cif", "dni", "destinatario_nif"),
    "entity_name": (
        "entity_name",
        "entity",
        "cliente",
        "razon_social",
        "destinatario",
    ),
    "title": ("title", "titulo", "asunto", "subject"),
    "download_status": ("download_status", "estado_descarga", "status"),
    "main_pdf_path": ("main_pdf_path", "pdf_path", "document_path", "documento_path"),
    "receipt_path": ("receipt_path", "acuse_path", "justificante_path"),
}


@dataclass(frozen=True)
class Match:
    row: dict[str, str] | None
    score: int
    reasons: list[str]
    debug: str = ""


@dataclass(frozen=True)
class IndexColumns:
    cliente: list[str]
    expediente: list[str]
    ruta: list[str]
    nif: list[str]

    def describe(self) -> str:
        parts = []
        for name in ("cliente", "expediente", "ruta", "nif"):
            values = getattr(self, name)
            parts.append(f"{name}={','.join(values) if values else '-'}")
        return " | ".join(parts)


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


def detect_delimiter(lines: list[str]) -> str:
    if lines and lines[0].strip().lower() == "sep=;":
        return ";"

    header = lines[0] if lines else ""
    return ";" if header.count(";") >= header.count(",") else ","


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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
    delimiter = detect_delimiter(lines)
    if lines and lines[0].strip().lower() == "sep=;":
        lines = lines[1:]

    reader = csv.DictReader(lines, delimiter=delimiter)
    return [clean_row(row) for row in reader]


def normalize(value: str) -> str:
    value = fix_mojibake(value or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.upper()
    value = re.sub(r"\bS\s*\.?\s*L\s*\.?\b", " SL ", value)
    value = re.sub(r"\bS\s*\.?\s*A\s*\.?\b", " SA ", value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def normalize_nif(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def remove_nifs(value: str) -> str:
    value = re.sub(r"\b[XYZ]?\d{7,8}[A-Z]\b", " ", value.upper())
    value = re.sub(r"\b[A-Z]\d{7,8}[A-Z0-9]\b", " ", value)
    return value


def name_tokens(value: str) -> list[str]:
    normalized = normalize(remove_nifs(value))
    return [
        token
        for token in normalized.split()
        if token not in COMPANY_FORM_TOKENS and token not in STOP_TOKENS and len(token) >= 3
    ]


def name_variants(value: str) -> set[str]:
    tokens = name_tokens(value)
    if not tokens:
        return set()
    variants = {" ".join(tokens), " ".join(sorted(tokens))}
    return {variant for variant in variants if variant}


def first_present(row: dict[str, str], aliases: Iterable[str]) -> str:
    normalized_keys = {normalize(key): key for key in row}

    for alias in aliases:
        key = normalized_keys.get(normalize(alias))
        if key and row.get(key):
            return row[key].strip()

    return ""


def detect_index_columns(rows: list[dict[str, str]]) -> IndexColumns:
    if not rows:
        return IndexColumns(cliente=[], expediente=[], ruta=[], nif=[])

    keys = list(rows[0].keys())
    by_norm = {normalize(key): key for key in keys}
    detected: dict[str, list[str]] = {}

    for group, aliases in INDEX_COLUMN_ALIASES.items():
        columns = []
        for alias in aliases:
            key = by_norm.get(normalize(alias))
            if key and key not in columns:
                columns.append(key)
        detected[group] = columns

    return IndexColumns(
        cliente=detected["cliente"],
        expediente=detected["expediente"],
        ruta=detected["ruta"],
        nif=detected["nif"],
    )


def values_from_columns(row: dict[str, str], columns: Iterable[str]) -> list[str]:
    values = []
    for column in columns:
        value = row.get(column, "").strip()
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
            if len(token) < 4:
                continue
            if token in STOP_TOKENS:
                continue
            if token in COMPANY_FORM_TOKENS:
                continue
            if token.isdigit():
                continue
            if re.fullmatch(r"[a-z]\d{7,8}[a-z0-9]", token):
                continue
            if re.fullmatch(r"[xyz]?\d{7,8}[a-z]", token):
                continue
            if re.fullmatch(r"20[2-3][0-9]", token):
                continue
            tokens.add(token)

    return tokens


def notification_value(row: dict[str, str], canonical: str) -> str:
    return first_present(row, NOTIFICATION_ALIASES[canonical])


def notification_client_values(row: dict[str, str]) -> list[str]:
    return [
        notification_value(row, "entity_name"),
        first_present(row, ("cliente_sugerido", "cliente", "cliente_detectado")),
    ]


def index_cliente(row: dict[str, str] | None, columns: IndexColumns) -> str:
    if not row:
        return ""
    return first_present(row, columns.cliente)


def index_expediente(row: dict[str, str] | None, columns: IndexColumns) -> str:
    if not row:
        return ""
    return first_present(row, columns.expediente)


def index_path(row: dict[str, str] | None, columns: IndexColumns) -> str:
    if not row:
        return ""
    return first_present(row, columns.ruta)


def index_nifs(row: dict[str, str], columns: IndexColumns) -> set[str]:
    values = values_from_columns(row, columns.nif)
    return {nif for value in values for nif in [normalize_nif(value)] if nif}


def client_match_score(notification_values: list[str], index_values: list[str]) -> tuple[int, str]:
    notif_variants = set()
    index_variants = set()

    for value in notification_values:
        notif_variants.update(name_variants(value))
    for value in index_values:
        index_variants.update(name_variants(value))

    if notif_variants and index_variants and notif_variants & index_variants:
        return 50, "cliente exacto/normalizado"

    notif_token_sets = [set(name_tokens(value)) for value in notification_values]
    index_token_sets = [set(name_tokens(value)) for value in index_values]

    best_overlap = set()
    for left in notif_token_sets:
        for right in index_token_sets:
            overlap = left & right
            if len(overlap) > len(best_overlap):
                best_overlap = overlap

    if len(best_overlap) >= 2:
        return 30, "cliente parcial: " + ", ".join(sorted(best_overlap))

    return 0, ""


def score_against_index(
    notification: dict[str, str],
    index_row: dict[str, str],
    columns: IndexColumns,
) -> Match:
    score = 0
    reasons: list[str] = []
    debug_parts: list[str] = []

    notif_nif = normalize_nif(notification_value(notification, "entity_nif"))
    row_nifs = index_nifs(index_row, columns)
    if notif_nif and row_nifs and notif_nif in row_nifs:
        score += 70
        reasons.append("NIF exacto")
    debug_parts.append(f"notif_nif={notif_nif or '-'}")
    debug_parts.append(f"index_nifs={','.join(sorted(row_nifs)) if row_nifs else '-'}")

    index_client_values = values_from_columns(index_row, columns.cliente)
    client_score, client_reason = client_match_score(
        notification_client_values(notification),
        index_client_values,
    )
    if client_score:
        score += client_score
        reasons.append(client_reason)

    notif_tokens = relevant_tokens(
        notification_value(notification, "title"),
        first_present(notification, ("procedure", "procedimiento", "numero_procedimiento")),
        first_present(notification, ("sender", "remitente", "organismo")),
    )
    index_tokens = relevant_tokens(
        unique_join(values_from_columns(index_row, columns.expediente)),
        unique_join(values_from_columns(index_row, columns.ruta)),
    )
    token_hits = sorted(notif_tokens & index_tokens)

    if token_hits:
        score += 20
        reasons.append("tokens significativos en expediente/ruta: " + ", ".join(token_hits[:8]))

    debug_parts.append("notif_tokens=" + (",".join(sorted(notif_tokens)) or "-"))
    debug_parts.append("index_tokens=" + (",".join(sorted(index_tokens)) or "-"))
    debug_parts.append("token_hits=" + (",".join(token_hits) or "-"))
    debug_parts.append("index_cliente=" + (unique_join(index_client_values) or "-"))

    return Match(row=index_row, score=min(score, 100), reasons=reasons, debug=" | ".join(debug_parts))


def best_match(
    notification: dict[str, str],
    index_rows: list[dict[str, str]],
    columns: IndexColumns,
) -> Match:
    best = Match(row=None, score=0, reasons=[], debug="")

    for index_row in index_rows:
        current = score_against_index(notification, index_row, columns)
        if current.score > best.score:
            best = current

    return best


def build_output_rows(
    notifications: list[dict[str, str]],
    index_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    columns = detect_index_columns(index_rows)
    columns_detected = columns.describe()

    for notification in notifications:
        match = best_match(notification, index_rows, columns)
        matched = match.row if match.row and match.score >= 50 else None
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
                "cliente_sugerido": index_cliente(matched, columns) if matched else "",
                "expediente_sugerido": index_expediente(matched, columns) if matched else "",
                "expediente_path": index_path(matched, columns) if matched else "",
                "match_score": str(match.score),
                "match_reason": " | ".join(match.reasons),
                "estado_asignacion": estado,
                "accion_sugerida": accion,
                "observaciones": "" if match.score >= 50 else "Sin match >=50 en indice vivo",
                "index_columns_detected": columns_detected,
                "match_debug": match.debug,
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


def print_summary(rows: list[dict[str, str]]) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        estado = row["estado_asignacion"]
        counts[estado] = counts.get(estado, 0) + 1

    print("Notificaciones:", len(rows))
    print("Resumen:", counts)
    print("Top 8:")
    ordered = sorted(rows, key=lambda row: int(row.get("match_score") or 0), reverse=True)
    for row in ordered[:8]:
        print(
            " - ".join(
                [
                    row.get("notification_id", ""),
                    row.get("estado_asignacion", ""),
                    row.get("match_score", ""),
                    row.get("cliente_sugerido", ""),
                    row.get("expediente_sugerido", ""),
                    row.get("match_reason", ""),
                ]
            )
        )


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

    notifications = read_csv_rows(notifica_inbox)
    index_rows = read_csv_rows(live_expedientes)
    output_rows = build_output_rows(notifications, index_rows)

    write_csv(output_rows, out_csv)
    write_xlsx(output_rows, out_xlsx)
    print_summary(output_rows)
    print("CSV:", out_csv)
    print("XLSX:", out_xlsx)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())





