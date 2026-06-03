# DespachoOps Index

Herramienta **separada** de [Autoarchivo](https://github.com/luisceb1/despachoops-autoarchivo): indexación de **solo lectura**, búsqueda, dashboard Excel, **OCR nocturno**, **Ollama** y **worker** (23:00–06:00).

## Reglas

No mueve, copia, renombra, borra ni reorganiza carpetas. Sin waves, apply ni rename.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows: Tesseract (`spa`) + Poppler para OCR; [Ollama](https://ollama.com) con `qwen3:8b` (o el modelo de `config.yaml`).

```bash
export PYTHONPATH=src
python -m despachoops_index.cli init --config config.yaml
python -m despachoops_index.cli doctor --config config.yaml
```

## CLI — MVP manual

```bash
python -m despachoops_index.cli index --root "RUTA" --db data/despacho_index.sqlite --limit 1000
python -m despachoops_index.cli index --root "RUTA" --db data/despacho_index.sqlite --limit 1000 --text
python -m despachoops_index.cli search "consulta" --db data/despacho_index.sqlite --limit 20
python -m despachoops_index.cli dashboard --db data/despacho_index.sqlite --output reports/index_dashboard.xlsx
```

Con `config.yaml` (producción):

```bash
python -m despachoops_index.cli index --config config.yaml --text
python -m despachoops_index.cli search "modelo 303" --config config.yaml
python -m despachoops_index.cli ocr-worker --config config.yaml
python -m despachoops_index.cli llm-enrich --config config.yaml
python -m despachoops_index.cli night-cycle --config config.yaml
python -m despachoops_index.cli worker --config config.yaml --once
```

## Ciclo nocturno

1. Índice incremental (lote `max_files_per_index_run`, solo cambios por `mtime`).
2. OCR → caché local (`max_files_per_ocr_run`).
3. Ollama → enriquecimiento desde SQLite/caché (**sin re-leer SMB**).

Ventana **23:00–06:00** + `require_idle_minutes` (Windows). SQLite y cachés en `C:\ProgramData\DespachoOps\Index`.

`catalog_each_night_cycle: false` evita barrido CSV completo cada noche (~192k archivos en SMB).

## Task Scheduler

```powershell
.\scripts\install_task_scheduler.ps1
```

## Estructura

```
src/despachoops_index/
  cli.py, config.py, indexer.py, search.py, dashboard.py
  ocr.py, ocr_worker.py, llm/, llm_enrichment.py
  night_runner.py, night_window.py, walk.py, safety.py, idle.py
config.yaml
scripts/
tests/
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

También funciona con `PYTHONPATH=src pytest` si no instalas el paquete en editable.

## gstack + Cursor (opcional)

[gstack](https://github.com/garrytan/gstack) aporta skills de revisión, depuración, documentación y release para el agente en Cursor. Tiene sentido en este repo para `/review`, `/investigate`, `/ship` y `/document-release`; las skills de diseño web o QA en navegador casi no aplican (CLI sin UI).

Instalación global (una vez):

```bash
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup -q && bun run gen:skill-docs --host cursor
```

Enlaza las skills generadas a `~/.cursor/skills/` (el script `setup` aún no incluye `--host cursor`; ver `AGENTS.md`).

Convenciones del proyecto para el agente: [AGENTS.md](AGENTS.md).
