# DespachoOps Index — ciclo nocturno (Task Scheduler 23:00–06:00)
# Ajusta $ProjectRoot y $Config antes de programar la tarea.

$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\ProyectosCoding\DespachoOps - Index"
$Config = Join-Path $ProjectRoot "config.yaml"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    $Python = "python"
}

Set-Location $ProjectRoot
& $Python despachoops_index.py night-cycle --config $Config
exit $LASTEXITCODE
