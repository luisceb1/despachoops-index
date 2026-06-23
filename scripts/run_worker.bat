@echo off
set LOGDIR=D:\DespachoOpsData\Index\logs

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGDIR%\scheduler_probe.log"
echo [%date% %time%] BAT START >> "%LOGDIR%\scheduler_probe.log"
echo Current dir before cd: %CD% >> "%LOGDIR%\scheduler_probe.log"

cd /d "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"

echo Current dir after cd: %CD% >> "%LOGDIR%\scheduler_probe.log"
echo Running PowerShell worker... >> "%LOGDIR%\scheduler_probe.log"

C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index\scripts\run_worker.ps1"

echo [%date% %time%] BAT END ERRORLEVEL=%ERRORLEVEL% >> "%LOGDIR%\scheduler_probe.log"

exit /b %ERRORLEVEL%