@echo off
title DespachoOps Index - Rebuild Web Cache

set LOGDIR=D:\DespachoOpsData\Index\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGDIR%\web_cache_rebuild.log"
echo [%date% %time%] START web cache rebuild >> "%LOGDIR%\web_cache_rebuild.log"

cd /d "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"

.\.venv\Scripts\python.exe -m despachoops_index.web.cache --config config.yaml >> "%LOGDIR%\web_cache_rebuild.log" 2>&1

echo [%date% %time%] END web cache rebuild ERRORLEVEL=%ERRORLEVEL% >> "%LOGDIR%\web_cache_rebuild.log"

exit /b %ERRORLEVEL%
