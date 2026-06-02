$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\ProyectosCoding\DespachoOps - Index"
$Config = Join-Path $ProjectRoot "config.yaml"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Set-Location $ProjectRoot
& $Python despachoops_index.py worker --config $Config --once
exit $LASTEXITCODE
