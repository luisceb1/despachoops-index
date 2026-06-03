# DespachoOps Index — ciclo nocturno: worker + dashboard histórico + latest
$ErrorActionPreference = "Stop"
$ProjectRoot = "C:\DespachoOps\despachoops-index"
$DataDir = "C:\DespachoOpsData\Index"
$ReportsDir = "\\Luiscp\d\Cebrian y Fraile Abogados\Index\reports"
$LatestDir = "\\Luiscp\d\Cebrian y Fraile Abogados\Index\latest"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $DataDir "logs"
$LogFile = Join-Path $LogDir "run_worker_$Stamp.log"

$env:PYTHONPATH = "$ProjectRoot\src"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

function Write-LogLine([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LatestDir | Out-Null

Set-Location $ProjectRoot
Write-LogLine "Inicio run_worker (DespachoOps Index)"

$ExitCode = 0

Write-LogLine "init (data_dir, logs, OCR, reports, latest)"
& $Python -m despachoops_index.cli --config config.yaml init
if ($LASTEXITCODE -ne 0) {
    Write-LogLine "init falló con código $LASTEXITCODE"
    $ExitCode = $LASTEXITCODE
}

Write-LogLine "worker --once"
& $Python -m despachoops_index.cli --config config.yaml worker --once
if ($LASTEXITCODE -ne 0) {
    Write-LogLine "worker falló con código $LASTEXITCODE"
    $ExitCode = $LASTEXITCODE
}

Write-LogLine "dashboard (reports con timestamp) + publish-latest"
& $Python -m despachoops_index.cli --config config.yaml dashboard --publish-latest
if ($LASTEXITCODE -ne 0) {
    Write-LogLine "dashboard falló con código $LASTEXITCODE"
    $ExitCode = $LASTEXITCODE
} else {
    Write-LogLine "latest publicado en $LatestDir\index_dashboard.xlsx"
}

Write-LogLine "Fin run_worker (exit=$ExitCode)"
exit $ExitCode
