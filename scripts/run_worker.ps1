$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\DespachoOps\despachoops-index"
$env:PYTHONPATH = "$ProjectRoot\src"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
Set-Location $ProjectRoot
& $Python -m despachoops_index.cli --config config.yaml worker --once
exit $LASTEXITCODE
