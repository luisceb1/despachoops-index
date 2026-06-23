from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


RESULT_PREFIX = "__DESPACHOOPS_RESULT_JSON__="


def parse_whitelist(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No existe whitelist: {path}")

    rows = []

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()

        if not raw:
            continue

        if raw.startswith("#"):
            continue

        parts = [p.strip() for p in raw.split("|")]

        if len(parts) < 2:
            raise ValueError(
                f"Línea {line_no} inválida. Formato: json_path|expediente|contains"
            )

        json_path = parts[0]
        expediente = parts[1]
        contains = parts[2] if len(parts) >= 3 else ""

        if not json_path:
            raise ValueError(f"Línea {line_no} sin json_path")

        if not expediente:
            raise ValueError(f"Línea {line_no} sin expediente")

        rows.append(
            {
                "json_path": json_path,
                "expediente": expediente,
                "contains": contains,
                "line_no": line_no,
            }
        )

    return rows


def parse_result_json(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            raw = line.split(RESULT_PREFIX, 1)[1].strip()
            return json.loads(raw)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--whitelist",
        default=r"D:\DespachoOpsData\Index\hydrate_expediente_whitelist.txt",
    )
    parser.add_argument(
        "--runs-dir",
        default=r"D:\DespachoOpsData\Index\hydrate_runs",
    )
    parser.add_argument("--limit", type=int, default=50)
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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    whitelist_path = Path(args.whitelist)
    rows = parse_whitelist(whitelist_path)
    rows = rows[: args.limit]

    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    audit_csv = runs_dir / f"hydrate_expedientes_{stamp}_{mode}.csv"

    hydrate_script = Path(__file__).with_name("hydrate_expediente_md_from_index.py")
    config_path = Path(args.config)

    print("Modo:", mode)
    print("Whitelist:", whitelist_path)
    print("Expedientes seleccionados:", len(rows))
    print("Audit CSV:", audit_csv)
    print("")

    for row in rows:
        print(
            row["line_no"],
            row["json_path"],
            "|",
            row["expediente"],
            "|",
            row["contains"],
        )

    failures = 0

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    with audit_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "mode",
                "line_no",
                "json_path",
                "expediente",
                "contains",
                "client_name",
                "client_dir",
                "expediente_dir",
                "md_path",
                "backup_path",
                "changed",
                "returncode",
                "result",
                "error",
            ],
        )
        writer.writeheader()

        for row in rows:
            cmd = [
                sys.executable,
                str(hydrate_script),
                row["json_path"],
                "--config",
                str(config_path),
                "--expediente",
                row["expediente"],
                "--json-result",
            ]

            if row["contains"]:
                cmd.extend(["--contains", row["contains"]])

            if args.dry_run:
                cmd.append("--dry-run")

            print("")
            print("==>", row["expediente"], "/", row["contains"])
            print(" ".join(f'"{x}"' if " " in x else x for x in cmd))

            result = subprocess.run(
                cmd,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            if stdout:
                print(stdout)

            if stderr:
                print(stderr)

            payload = parse_result_json(stdout)

            if result.returncode != 0 or not payload.get("ok"):
                failures += 1
                status = "ERROR"
                error = payload.get("error") or (stderr or stdout or "").strip()[-1000:]
                print(
                    "ERROR:",
                    row["expediente"],
                    row["contains"],
                    "returncode=",
                    result.returncode,
                )
            else:
                status = "OK"
                error = ""

            writer.writerow(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "mode": mode,
                    "line_no": row["line_no"],
                    "json_path": row["json_path"],
                    "expediente": row["expediente"],
                    "contains": row["contains"],
                    "client_name": payload.get("client_name", ""),
                    "client_dir": payload.get("client_dir", ""),
                    "expediente_dir": payload.get("expediente_dir", ""),
                    "md_path": payload.get("md_path", ""),
                    "backup_path": payload.get("backup_path", ""),
                    "changed": payload.get("changed", ""),
                    "returncode": result.returncode,
                    "result": status,
                    "error": error,
                }
            )

    print("")
    print("Audit CSV:", audit_csv)
    print("OK" if failures == 0 else "FINALIZADO CON ERRORES")
    print("Errores:", failures)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())