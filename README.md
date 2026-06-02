# DespachoOps Index

Herramienta de **solo lectura** para indexar y buscar la base documental del despacho, inspirada en [DespachoOps Autoarchivo](https://github.com/luisceb1/despachoops-autoarchivo). **No mueve, copia, renombra ni reestructura carpetas.**

Árbol indexado (producción):

`\\Luiscp\d\Cebrian y Fraile Abogados\Clientes`

Metadatos, SQLite, cola OCR, enriquecimiento LLM y logs viven en disco **local** (`C:\ProgramData\DespachoOps\Index` por defecto) para evitar bloqueos SMB.

## Ciclo nocturno (23:00–06:00)

Orden por defecto en `night-cycle` / `worker`:

1. **Índice SQLite + FTS5** — barrido incremental (solo archivos nuevos/modificados por `mtime`).
2. **OCR** — hasta `max_files_per_ocr_run` PDF/imágenes; caché local.
3. **Ollama** — hasta `llm.max_files_per_run` documentos usando **texto ya en SQLite o caché OCR** (no re-lee SMB).

El **catálogo CSV completo** está **desactivado** en el ciclo nocturno (`catalog_each_night_cycle: false`) porque recorrería ~192k archivos en red cada noche. Ejecútalo manualmente cuando haga falta: `python despachoops_index.py catalog`.

Condiciones de ejecución:

- Ventana `night_window_start` – `night_window_end` (por defecto **23:00–06:00**).
- Opcional: `require_idle_minutes` (Windows: tiempo sin input del usuario).

## Instalación (Windows)

```powershell
cd "C:\ProyectosCoding\DespachoOps - Index"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python despachoops_index.py init
python despachoops_index.py doctor --config config.yaml
```

- **OCR:** [Tesseract](https://github.com/tesseract-ocr/tesseract) (`spa`) + [Poppler](https://blog.alivate.com.au/poppler-windows/).
- **LLM:** [Ollama](https://ollama.com) en `http://localhost:11434` con el modelo de `config.yaml` (p. ej. `qwen3:8b`).

```powershell
ollama pull qwen3:8b
```

## Comandos

| Comando | Descripción |
|---------|-------------|
| `doctor` | Red, ventana, Tesseract, Ollama, pendientes LLM |
| `catalog` | CSV inventario completo (uso puntual; carga SMB alta) |
| `index` | Actualiza SQLite incremental |
| `search "modelo 303"` | Búsqueda (incluye resumen LLM si existe) |
| `ocr-worker` | Lote OCR nocturno |
| `llm-enrich` | Lote Ollama (solo texto local) |
| `night-cycle` | Índice + OCR + LLM |
| `worker --once` | Un ciclo; Task Scheduler lo repite |

## Ollama (`llm` en config.yaml)

Por documento, el modelo devuelve JSON: `tipo_documental`, `area`, `resumen`, `palabras_clave`, `confianza`, `necesita_revision`. Se guarda en la tabla `llm_enrichment` del SQLite local.

- **Lote pequeño** (`max_files_per_run: 20`) para no competir con OCR/RAM.
- **`release_model_after_batch: true`** libera VRAM tras cada ciclo.
- Los datos sensibles **no salen del PC** si Ollama es local.

## Automatización

```powershell
.\scripts\install_task_scheduler.ps1
```

## Riesgos y mitigaciones

| Riesgo | Mitigación en Index |
|--------|---------------------|
| **SMB saturado** | Lotes index 5000 / OCR 150 / LLM 20; ventana 23:00–06:00; catálogo nocturno off |
| **SQLite en red** | Solo `data_dir` local |
| **Privacidad** | Índice, OCR cache y LLM en `C:\ProgramData\DespachoOps\Index`; proteger permisos NTFS |
| **OCR CPU/RAM** | Pocas páginas; cola incremental |
| **LLM CPU/RAM** | Pocos archivos/ciclo; modelo pequeño; `release_model_after_batch` |
| **Inactividad** | `require_idle_minutes: 10` (Windows) |
| **Primer índice ~192k** | Varios días; subir límites poco a poco |

El módulo `safety` impide escribir bajo `scan_root`.

## Desarrollo

```bash
pytest
```
