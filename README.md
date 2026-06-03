# DespachoOps Index

Herramienta **separada** de [Autoarchivo](https://github.com/luisceb1/despachoops-autoarchivo): indexación de **solo lectura**, búsqueda, dashboard Excel, **OCR nocturno**, **Ollama** y **worker** (23:00–06:00).

## Reglas

No mueve, copia, renombra, borra ni reorganiza carpetas. Sin waves, apply ni rename.

## Producción (Windows)

| Qué | Ruta |
|-----|------|
| Código | `C:\DespachoOps\despachoops-index` |
| Motor local (SQLite, OCR, logs, lock) | `C:\DespachoOpsData\Index` |
| Resultados compartidos (raíz) | `\\Luiscp\d\Cebrian y Fraile Abogados\Index` |
| Reports históricos | `\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports` |
| Dashboard actual | `\\Luiscp\d\Cebrian y Fraile Abogados\Index\latest\index_dashboard.xlsx` |
| Documentos (**solo lectura**) | `\\Luiscp\d\Cebrian y Fraile Abogados\Clientes` |

**Importante:** solo un PC debe ejecutar el worker nocturno. El resto consulta los Excel en `Index\reports` y `Index\latest`.

Nunca escribir bajo `Clientes`. No guardar SQLite, OCR ni logs en SMB.

### Instalación y primer arranque

```powershell
cd C:\DespachoOps\despachoops-index
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml init
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml doctor
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml index --limit 5000 --text --force
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard
```

Índice grande (20.000):

```powershell
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml index --limit 20000 --text --force
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard --publish-latest
```

Dashboard con ruta explícita y publicación en latest:

```powershell
.\.venv\Scripts\python.exe -m despachoops_index.cli --config config.yaml dashboard --output "\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports\index_dashboard_20000.xlsx" --publish-latest
```

Sin `--output`, guarda `index_dashboard_YYYYMMDD_HHMMSS.xlsx` en `reports_dir`. Con `--publish-latest`, copia también a `latest_dir\index_dashboard.xlsx`.

### Worker nocturno (`scripts\run_worker.ps1`)

1. Crea `C:\DespachoOpsData\Index\logs`, `Index\reports` e `Index\latest` si faltan.
2. `init` + `worker --once`.
3. `dashboard --publish-latest` (histórico con timestamp + latest fijo).
4. Log en `C:\DespachoOpsData\Index\logs\run_worker_YYYYMMDD_HHMMSS.log`.
5. Exit code distinto de 0 si falla worker o dashboard.

```powershell
.\scripts\run_worker.ps1
```

### Task Scheduler

```powershell
.\scripts\install_task_scheduler.ps1
```

Tarea `DespachoOps-Index-Night`: 23:00, cada 10 min durante 8 h, ejecuta `run_worker.ps1`.

## CLI

`--config config.yaml` va **antes** del subcomando.

Correcto:

```powershell
python -m despachoops_index.cli --config config.yaml doctor
```

Incorrecto:

```powershell
python -m despachoops_index.cli doctor --config config.yaml
```

## config.yaml (campos de rutas)

```yaml
scan_root: '\\Luiscp\d\Cebrian y Fraile Abogados\Clientes'
data_dir: 'C:/DespachoOpsData/Index'
shared_output_dir: '\\Luiscp\d\Cebrian y Fraile Abogados\Index'
reports_dir: '\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports'
latest_dir: '\\Luiscp\d\Cebrian y Fraile Abogados\Index\latest'
```

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

MVP sin config:

```bash
python -m despachoops_index.cli index --root "RUTA" --db data/despacho_index.sqlite --text
python -m despachoops_index.cli dashboard --db data/despacho_index.sqlite --output reports/dash.xlsx
```

## Ciclo nocturno

1. Índice incremental (`max_files_per_index_run`).
2. OCR → caché local.
3. Ollama → enriquecimiento desde SQLite/caché (sin re-leer SMB).

Ventana **23:00–06:00** + `require_idle_minutes`.

## Estructura

```
src/despachoops_index/
  cli.py, config.py, indexer.py, search.py, dashboard.py
  ocr.py, ocr_worker.py, llm/, night_runner.py, safety.py, walk.py
config.yaml
scripts/run_worker.ps1
scripts/install_task_scheduler.ps1
tests/
```

## gstack + Cursor (opcional)

Ver [AGENTS.md](AGENTS.md).
