from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_EXCLUDE_CLIENT_NAMES = {
    "IRPF",
    "AEAT",
    "Cuentas Anuales",
    "Index",
    "Notificaciones",
    "Modelos",
    "Plantillas",
    "General",
}


def normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def load_name_file(path: str) -> set[str]:
    if not path:
        return set()

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"No existe fichero: {file_path}")

    names = set()
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        names.add(normalize_name(line))

    return names


def extract_md_path(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("Markdown:"):
            return line.split("Markdown:", 1)[1].strip()
    return ""


def extract_backup_path(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("Backup:"):
            return line.split("Backup:", 1)[1].strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default=r"D:\DespachoOpsData\Index\client_context_index\_index.json")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-documents", type=int, default=10)
    parser.add_argument("--only-with-deadlines", action="store_true")
    parser.add_argument("--whitelist", default="")
    parser.add_argument("--blacklist", default=r"D:\DespachoOpsData\Index\hydrate_blacklist.txt")
    parser.add_argument("--runs-dir", default=r"D:\DespachoOpsData\Index\hydrate_runs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.write and args.dry_run:
        print("ERROR: usa --dry-run o --write, no ambos.")
        return 1

    if not args.write and not args.dry_run:
        print("ERROR: por seguridad, debes indicar --dry-run o --write.")
        return 1

    mode = "write" if args.write else "dry-run"
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    audit_csv = runs_dir / f"hydrate_{stamp}_{mode}.csv"

    index_path = Path(args.index)
    data = json.loads(index_path.read_text(encoding="utf-8"))

    whitelist = load_name_file(args.whitelist)
    blacklist = load_name_file(args.blacklist) if Path(args.blacklist).exists() else set()

    if whitelist:
        print("Whitelist activa:", args.whitelist)
        print("Clientes en whitelist:", len(whitelist))
        print("")

    if blacklist:
        print("Blacklist activa:", args.blacklist)
        print("Clientes/carpetas en blacklist:", len(blacklist))
        print("")

    clients = data.get("clients", [])

    selected = []
    skipped_not_in_whitelist = 0
    skipped_blacklist = 0
    skipped_default_exclude = 0

    for c in clients:
        name = c.get("client_name", "")
        docs = int(c.get("ocr_documents", 0) or 0)
        deadlines = int(c.get("documents_with_deadlines", 0) or 0)
        normalized = normalize_name(name)

        if name in DEFAULT_EXCLUDE_CLIENT_NAMES or normalized in {
            normalize_name(x) for x in DEFAULT_EXCLUDE_CLIENT_NAMES
        }:
            skipped_default_exclude += 1
            continue

        if normalized in blacklist:
            skipped_blacklist += 1
            continue

        if whitelist and normalized not in whitelist:
            skipped_not_in_whitelist += 1
            continue

        if docs < args.min_documents:
            continue

        if args.only_with_deadlines and deadlines <= 0:
            continue

        selected.append(c)

    selected.sort(
        key=lambda x: (
            int(x.get("documents_with_deadlines", 0) or 0),
            int(x.get("ocr_documents", 0) or 0),
        ),
        reverse=True,
    )

    selected = selected[: args.limit]

    print("Modo:", mode)
    print("Clientes seleccionados:", len(selected))
    if whitelist:
        print("Omitidos por no estar en whitelist:", skipped_not_in_whitelist)
    print("Omitidos por blacklist:", skipped_blacklist)
    print("Omitidos por exclusión interna:", skipped_default_exclude)
    print("Audit CSV:", audit_csv)
    print("")

    for c in selected:
        print(
            c.get("ocr_documents", 0),
            c.get("documents_with_deadlines", 0),
            c.get("client_name", ""),
            c.get("path", ""),
        )

    print("")
    print("Ejecutando...")

    hydrate_script = Path(__file__).with_name("hydrate_client_md_from_index.py")
    config_path = Path(args.config)

    failures = 0

    with audit_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "mode",
                "client_name",
                "ocr_documents",
                "documents_with_deadlines",
                "json_path",
                "md_path",
                "backup_path",
                "returncode",
                "result",
                "error",
            ],
        )
        writer.writeheader()

        for c in selected:
            client_name = c.get("client_name", "")
            json_path = c.get("path", "")
            docs = int(c.get("ocr_documents", 0) or 0)
            deadlines = int(c.get("documents_with_deadlines", 0) or 0)

            if not json_path:
                failures += 1
                writer.writerow(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "mode": mode,
                        "client_name": client_name,
                        "ocr_documents": docs,
                        "documents_with_deadlines": deadlines,
                        "json_path": json_path,
                        "md_path": "",
                        "backup_path": "",
                        "returncode": 1,
                        "result": "ERROR",
                        "error": "Cliente sin path JSON",
                    }
                )
                continue

            cmd = [
                sys.executable,
                str(hydrate_script),
                json_path,
                "--config",
                str(config_path),
            ]

            if args.dry_run:
                cmd.append("--dry-run")

            print("")
            print("==>", client_name)
            print(" ".join(f'"{x}"' if " " in x else x for x in cmd))

            result = subprocess.run(
                cmd,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )

            if result.stdout:
                print(result.stdout)

            if result.stderr:
                print(result.stderr)

            md_path = extract_md_path(result.stdout or "")
            backup_path = extract_backup_path(result.stdout or "")

            if result.returncode != 0:
                failures += 1
                status = "ERROR"
                error = (result.stderr or result.stdout or "").strip()[-1000:]
                print("ERROR:", client_name, "returncode=", result.returncode)
            else:
                status = "OK"
                error = ""

            writer.writerow(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "mode": mode,
                    "client_name": client_name,
                    "ocr_documents": docs,
                    "documents_with_deadlines": deadlines,
                    "json_path": json_path,
                    "md_path": md_path,
                    "backup_path": backup_path,
                    "returncode": result.returncode,
                    "result": status,
                    "error": error,
                }
            )

    print("")
    print("Inicio:", started_at)
    print("Fin:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("Audit CSV:", audit_csv)
    print("OK" if failures == 0 else "FINALIZADO CON ERRORES")
    print("Errores:", failures)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())