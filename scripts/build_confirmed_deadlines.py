from __future__ import annotations

import argparse
import csv
from pathlib import Path


def fix_mojibake(value: str) -> str:
    if not isinstance(value, str):
        return value

    # Corrige casos típicos: NotificaciÃ³n -> Notificación
    if "Ã" in value or "Â" in value:
        try:
            return value.encode("latin1").decode("utf-8")
        except Exception:
            return value

    return value


def clean_row(row: dict) -> dict:
    return {k: fix_mojibake(v) for k, v in row.items()}


def read_semicolon_csv(path: Path) -> list[dict]:
    last_error = None

    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as e:
            last_error = e
    else:
        raise last_error

    lines = text.splitlines()
    if lines and lines[0].strip().lower() == "sep=;":
        text = "\n".join(lines[1:])

    reader = csv.DictReader(text.splitlines(), delimiter=";")
    return [clean_row(row) for row in reader]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=r"D:\DespachoOpsData\Index\deadline_candidates_reviewed.csv",
    )
    parser.add_argument(
        "--output",
        default=r"D:\DespachoOpsData\Index\confirmed_deadlines.csv",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = read_semicolon_csv(input_path)

    confirmed = []

    for row in rows:
        estado = (row.get("estado_revision") or "").strip().lower()

        if estado != "confirmado":
            continue

        confirmed.append(
            {
                "estado": "confirmado",
                "cliente": row.get("cliente", ""),
                "expediente": row.get("expediente", ""),
                "contains": row.get("contains", ""),
                "riesgo": row.get("riesgo", ""),
                "tipo": row.get("tipo", ""),
                "archivo": row.get("archivo", ""),
                "plazo_detectado": row.get("plazo_detectado", ""),
                "fechas_detectadas": row.get("fechas_detectadas", ""),
                "procedimientos": row.get("procedimientos", ""),
                "importes": row.get("importes", ""),
                "ruta": row.get("ruta", ""),
                "observaciones": row.get("observaciones", ""),
                "fecha_notificacion": "",
                "fecha_vencimiento": "",
                "actuacion": "",
                "responsable": "",
                "estado_plazo": "pendiente",
                "calendar_event_id": "",
            }
        )

    fieldnames = [
        "estado",
        "estado_plazo",
        "cliente",
        "expediente",
        "contains",
        "riesgo",
        "tipo",
        "archivo",
        "plazo_detectado",
        "fecha_notificacion",
        "fecha_vencimiento",
        "actuacion",
        "responsable",
        "fechas_detectadas",
        "procedimientos",
        "importes",
        "ruta",
        "observaciones",
        "calendar_event_id",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        f.write("sep=;\n")
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(confirmed)

    print("Candidatos revisados:", len(rows))
    print("Plazos confirmados:", len(confirmed))
    print("CSV:", output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())