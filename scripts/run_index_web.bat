@echo off
title DespachoOps Index Lite

cd /d C:\DespachoOps\despachoops-index

echo Iniciando DespachoOps Index Lite en red local...
echo.
echo Local:
echo http://127.0.0.1:8765
echo.
echo Red:
echo http://%COMPUTERNAME%:8765
echo.

start "" http://127.0.0.1:8765

.\.venv\Scripts\python.exe -m despachoops_index.web.app --config config.yaml --host 0.0.0.0 --port 8765

pause