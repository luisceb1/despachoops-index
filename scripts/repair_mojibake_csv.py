from __future__ import annotations

import argparse
from pathlib import Path


def fix_mojibake(value: str) -> str:
    if "Ã" in value or "Â" in value:
        try:
            return value.encode("latin1").decode("utf-8")
        except Exception:
            return value
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = input_path.read_text(encoding="utf-8-sig")
    fixed = fix_mojibake(text)

    output_path.write_text(fixed, encoding="utf-8-sig", newline="")

    print("Entrada:", input_path)
    print("Salida:", output_path)
    print("Contenía mojibake:", ("Ã" in text or "Â" in text))
    print("Sigue con mojibake:", ("Ã" in fixed or "Â" in fixed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())