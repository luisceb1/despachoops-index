$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\ProyectosCoding\DespachoOps - Index"
$env:PYTHONPATH = "$ProjectRoot\src"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
Set-Location $ProjectRoot
& $Python -m despachoops_index.cli night-cycle --config config.yaml
exit $LASTEXITCODE
