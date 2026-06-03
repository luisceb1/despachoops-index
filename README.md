# DespachoOps Index

Herramienta **separada** de [Autoarchivo](https://github.com/luisceb1/despachoops-autoarchivo): indexación de **solo lectura**, búsqueda, dashboard Excel, **OCR nocturno**, **Ollama** y **worker** (23:00–06:00).

## Reglas

No mueve, copia, renombra, borra ni reorganiza carpetas. Sin waves, apply ni rename.

**Rutas de producción (Windows):**

| Qué | Dónde |
|-----|--------|
| Código | `C:\DespachoOps\despachoops-index` |
| SQLite, OCR cache, logs, cola, lock | `C:\DespachoOpsData\Index` (solo disco local) |
| Dashboards Excel | `\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports` |
| Documentos (solo lectura) | `\\Luiscp\d\Cebrian y Fraile Abogados\Clientes` |

Nunca escribir en `scan_root`. No guardar SQLite, OCR ni logs en SMB.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows: Tesseract (`spa`) + Poppler para OCR; [Ollama](https://ollama.com) con `qwen3:8b` (o el modelo de `config.yaml`).

## Producción (PowerShell)

```powershell
cd C:\DespachoOps\despachoops-index
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml init
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml doctor
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml index --limit 5000 --text --force
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard
```

Índice grande (20.000 archivos) y dashboard:

```powershell
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml index --limit 20000 --text --force
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard
```

Dashboard con nombre explícito en red:

```powershell
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard --output "\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports\index_dashboard_20000.xlsx"
```

Sin `--output`, el dashboard se guarda como `index_dashboard_YYYYMMDD_HHMMSS.xlsx` en `reports_dir`.

## CLI — desarrollo local

`--config config.yaml` va **antes** del subcomando:

```bash
export PYTHONPATH=src
python -m despachoops_index.cli --config config.yaml init
python -m despachoops_index.cli --config config.yaml doctor
```

MVP manual (sin config):

```bash
python -m despachoops_index.cli index --root "RUTA" --db data/despacho_index.sqlite --limit 1000
python -m despachoops_index.cli index --root "RUTA" --db data/despacho_index.sqlite --limit 1000 --text
python -m despachoops_index.cli search "consulta" --db data/despacho_index.sqlite --limit 20
python -m despachoops_index.cli dashboard --db data/despacho_index.sqlite --output reports/index_dashboard.xlsx
```

Con `config.yaml`:

```powershell
python -m despachoops_index.cli --config config.yaml index --text
python -m despachoops_index.cli --config config.yaml search "modelo 303" --limit 20
python -m despachoops_index.cli --config config.yaml ocr-worker --force
python -m despachoops_index.cli --config config.yaml llm-enrich --force
python -m despachoops_index.cli --config config.yaml night-cycle --force
python -m despachoops_index.cli --config config.yaml worker --once
```

## Ciclo nocturno

1. Índice incremental (lote `max_files_per_index_run`, solo cambios por `mtime`).
2. OCR → caché local (`max_files_per_ocr_run`).
3. Ollama → enriquecimiento desde SQLite/caché (**sin re-leer SMB**).

Ventana **23:00–06:00** + `require_idle_minutes` (Windows).

`catalog_each_night_cycle: false` evita barrido CSV completo cada noche (~192k archivos en SMB).

## Task Scheduler

```powershell
.\scripts\install_task_scheduler.ps1
```

Ejecuta `scripts\run_worker.ps1` → `python -m despachoops_index.cli --config config.yaml worker --once`.

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
