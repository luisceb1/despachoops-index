# DespachoOps Index — guía para agentes

Herramienta Python de **solo lectura**: indexación, búsqueda, OCR nocturno, enriquecimiento Ollama y worker. No mueve, copia, renombra ni borra archivos en las rutas indexadas.

## gstack (instalado globalmente en Cursor)

Este repo usa [gstack](https://github.com/garrytan/gstack) en `~/.cursor/skills/` para flujos de revisión, depuración, documentación y release. Instalación global:

```bash
test -d ~/.cursor/skills/gstack/bin && echo OK || echo "Falta gstack: ver README sección gstack"
```

### Skills recomendados para este proyecto

| Cuándo | Skill (Cursor) | Motivo |
|--------|----------------|--------|
| Revisar cambios antes de merge | `gstack-review` | Seguridad SQL, efectos colaterales, regresiones en indexer/OCR/LLM |
| Depurar fallos en worker o night-cycle | `gstack-investigate` | RCA sistemático sin parches a ciegas |
| Cerrar feature con tests y PR | `gstack-ship` | Ejecuta `pytest`, audita cobertura, abre PR |
| Actualizar README tras un release | `gstack-document-release` | Mantiene docs alineados con el diff |
| Cambios de arquitectura (indexer, SQLite, SMB) | `gstack-plan-eng-review` | Flujos, estados, fallos, matriz de tests |
| Operaciones sensibles (rutas SMB, `config.yaml`) | `gstack-careful` o `gstack-guard` | Evita comandos destructivos fuera de alcance |
| Auditoría de seguridad puntual | `gstack-cso` | OWASP/STRIDE en código que toca rutas o credenciales |

### Skills poco relevantes aquí

No hay UI web ni despliegue frontend: omitir por defecto `gstack-qa`, `gstack-design-*`, `gstack-browse`, `gstack-office-hours` salvo que el usuario lo pida explícitamente.

### Reglas de dominio (obligatorias)

1. Respetar `safety.py` y las reglas del README: **nunca** escribir, mover o borrar en las raíces indexadas.
2. Preferir cambios acotados en `src/despachoops_index/`, `tests/`, `config.yaml` y scripts documentados.
3. Tras cambios de comportamiento: `pytest` (editable: `pip install -e ".[dev]"`).
4. Rutas Windows/SMB y ventana nocturna están en `config.yaml`; no asumir macOS en producción.

### Cómo invocar en Cursor

Pide en lenguaje natural, por ejemplo: «revisa este diff con gstack-review», «investiga por qué falla ocr-worker», «documenta el release con gstack-document-release». El agente debe cargar el `SKILL.md` correspondiente en `~/.cursor/skills/gstack-<nombre>/`.

### Actualizar gstack

```bash
cd ~/.claude/skills/gstack && git pull && ./setup -q && bun run gen:skill-docs --host cursor
# Re-enlazar a ~/.cursor/skills si hace falta (ver instalación en README)
```
