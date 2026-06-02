# DespachoOps Index

Herramienta de **solo lectura** para indexar y buscar la base documental del despacho, inspirada en [DespachoOps Autoarchivo](https://github.com/luiscebrianfraile/despachoops-autoarchivo). **No mueve, copia, renombra ni reestructura carpetas.**

Árbol indexado (producción):

`\\Luiscp\d\Cebrian y Fraile Abogados\Clientes`

Metadatos, SQLite, cola OCR y logs viven en disco **local** (`C:\ProgramData\DespachoOps\Index` por defecto) para evitar bloqueos SMB.

## Qué hace por la noche (23:00–06:00)

1. **Inventario CSV** — listado de archivos con cliente/área/año inferidos por ruta.
2. **Índice SQLite + FTS5** — rutas, metadatos y texto (PDF nativo, Office, caché OCR).
3. **Cola OCR** — PDFs escaneados e imágenes; Tesseract + Poppler; caché en `data_dir`.

Solo corre si:

- Hora dentro de `night_window_start` / `night_window_end` (por defecto **23:00–06:00**).
- Opcional: usuario inactivo ≥ `require_idle_minutes` (Windows: último input).

## Instalación (Windows)

```powershell
cd "C:\ProyectosCoding\DespachoOps - Index"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python despachoops_index.py init
python despachoops_index.py doctor --config config.yaml
```

Ajusta `scan_root` en `config.yaml` si la unidad de red se monta con otra letra.

OCR opcional: [Tesseract](https://github.com/tesseract-ocr/tesseract) (`spa`) y [Poppler](https://blog.alivate.com.au/poppler-windows/) en el PATH.

## Comandos

| Comando | Descripción |
|---------|-------------|
| `doctor` | Comprueba acceso a red, ventana horaria y Tesseract |
| `catalog` | CSV de inventario (solo lectura) |
| `index` | Actualiza SQLite incremental |
| `search "modelo 303"` | Búsqueda en índice |
| `ocr-worker` | Procesa lote OCR nocturno |
| `night-cycle` | Catálogo + índice + OCR (un ciclo) |
| `worker --once` | Un ciclo si está en ventana; Task Scheduler lo repite |

## Automatización

```powershell
# Una vez, como admin (ajusta rutas en install_task_scheduler.ps1)
.\scripts\install_task_scheduler.ps1
```

La tarea ejecuta `worker --once` cada 10 minutos entre las 23:00 y ~07:00; Python **no hace nada** fuera de la ventana.

Ciclo manual:

```powershell
.\scripts\run_night_cycle.ps1
```

## Riesgos importantes

| Riesgo | Mitigación |
|--------|------------|
| **Carga en SMB** (`\\Luiscp\d\...`) | Lotes (`max_files_per_index_run`, `max_files_per_ocr_run`); ventana nocturna; idle |
| **Antivirus / indexación Windows** | Puede ralentizar el primer barrido; excluir solo `data_dir` local si el AV lo permite |
| **SQLite en red** | Prohibido por diseño: DB solo en `data_dir` local |
| **Lectura intensiva de PDF** | `index_skip_large_files_mb` / `ocr_skip_large_files_mb` |
| **OCR CPU/RAM** | Pocas páginas por archivo; cola incremental |
| **Privacidad** | Texto en SQLite y `ocr_cache` en disco local; proteger `C:\ProgramData\DespachoOps\Index` |
| **Primer índice completo** | Puede tardar días con ~192k archivos; subir límites gradualmente |
| **LLM** | No incluido en v0.1; Autoarchivo tiene `llm-review-candidates` aparte. Index deja texto listo para búsqueda/OCR |

El módulo `safety` bloquea cualquier escritura bajo `scan_root`.

## Relación con Autoarchivo

| Autoarchivo | Index |
|-------------|-------|
| Clasifica, copia, archiva | Solo indexa y extrae texto |
| `input_dir` / entrada | `scan_root` = carpeta Clientes real |
| `index` + `ocr-worker` | Misma idea, proyecto dedicado |

Puedes usar el índice para buscar expedientes antes de archivar con Autoarchivo.

## Desarrollo

```bash
pytest
```
