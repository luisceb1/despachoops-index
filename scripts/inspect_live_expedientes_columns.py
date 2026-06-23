import csv
from pathlib import Path

p = Path("//Luiscp/d/DespachoOpsData/Index/live_expedientes_index.csv")

with p.open("r", encoding="utf-8-sig", newline="") as f:
    first = f.readline()
    if not first.lower().startswith("sep="):
        f.seek(0)
    reader = csv.DictReader(f, delimiter=";")
    rows = list(reader)
    fieldnames = reader.fieldnames or []

print("COLUMNAS:")
for c in fieldnames:
    print("-", c)

print()
print("FILAS:", len(rows))

print()
print("MUESTRA:")
for r in rows[:5]:
    print({k: r.get(k, "") for k in fieldnames[:10]})