import csv
import json
import unicodedata
from pathlib import Path

NOTIFICA = Path("C:/DespachoOpsData/Notifica/notificaciones_inbox.csv")
CTX_DIR = Path("//Luiscp/d/DespachoOpsData/Index/client_context_index")


def norm(s: str) -> str:
    s = str(s or "").upper()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return s


def read_csv_flexible(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if lines and lines[0].lower().startswith("sep="):
        lines = lines[1:]
    sample = "\n".join(lines[:5])
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    return list(csv.DictReader(lines, delimiter=delimiter))


notifs = read_csv_flexible(NOTIFICA)

contexts = []
for p in CTX_DIR.glob("*.json"):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    blob = norm(json.dumps(data, ensure_ascii=False))
    contexts.append((p, blob, data))

print("NOTIFICACIONES:", len(notifs))
print("CONTEXTOS JSON:", len(contexts))
print()

for n in notifs:
    nid = n.get("id") or n.get("notification_id") or ""
    nif = norm(n.get("entity_nif", ""))
    name = norm(n.get("entity_name", "") or n.get("cliente_sugerido", ""))
    title = n.get("title", "")

    print("=" * 80)
    print("ID:", nid)
    print("NIF:", nif)
    print("NAME:", name)
    print("TITLE:", title[:120])

    matches = []

    for p, blob, data in contexts:
        score = 0
        reasons = []

        if nif and nif in blob:
            score += 100
            reasons.append("NIF en JSON")

        if name:
            name_tokens = [t for t in name.split() if len(t) >= 4]
            hit_tokens = [t for t in name_tokens if t in blob]
            if len(hit_tokens) >= 2:
                score += 40
                reasons.append("tokens nombre: " + ", ".join(hit_tokens[:5]))
            elif len(hit_tokens) == 1:
                score += 15
                reasons.append("token nombre: " + hit_tokens[0])

        if score:
            matches.append((score, str(p), "; ".join(reasons)))

    matches.sort(reverse=True)

    if not matches:
        print("MATCHES: ninguno")
    else:
        print("MATCHES:")
        for score, path, reason in matches[:5]:
            print(f"  {score:>3} | {reason} | {path}")