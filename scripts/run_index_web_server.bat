@echo off
title DespachoOps Index Lite - Servidor Luiscp

cd /d "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"

echo ============================================
echo DespachoOps Index Lite - Servidor Luiscp
echo ============================================
echo.
echo Local:
echo http://127.0.0.1:8765
echo.
echo Red:
echo http://luiscp:8765
echo.
echo NO CIERRES ESTA VENTANA mientras quieras usar el buscador.
echo.

.\.venv\Scripts\python.exe -m despachoops_index.web.app --config config.yaml --host 0.0.0.0 --port 8765

pause
