# DespachoOps Index — mantenimiento manual de expediente vivo
$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"
$DataDir = "D:\DespachoOpsData\Index"
$LogDir = Join-Path $DataDir "logs"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "live_expedientes_maintenance_$Stamp.log"

$Python = "$ProjectRoot\.venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config.yaml"

$ClientWhitelist = Join-Path $DataDir "hydrate_whitelist.txt"
$ClientBlacklist = Join-Path $DataDir "hydrate_blacklist.txt"
$ExpedienteWhitelist = Join-Path $DataDir "hydrate_expediente_whitelist.txt"
$LiveExpedientesIndex = Join-Path $DataDir "live_expedientes_index.csv"
$DeadlineCandidates = Join-Path $DataDir "deadline_candidates.csv"
$ConfirmedDeadlinesWorking = Join-Path $DataDir "confirmed_deadlines_working.csv"
$DeadlineControlReport = Join-Path $DataDir "deadline_control_report.xlsx"

$env:PYTHONPATH = "$ProjectRoot\src"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path $Python)) {
    $Python = "python"
}

function Write-LogLine([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Run-Step([string]$Name, [scriptblock]$Command) {
    Write-LogLine $Name
    & $Command 2>&1 | ForEach-Object {
        Write-LogLine $_
    }

    if ($LASTEXITCODE -ne 0) {
        Write-LogLine "$Name falló con código $LASTEXITCODE"
        return $LASTEXITCODE
    }

    return 0
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $ProjectRoot)) {
    Write-Host "No existe ProjectRoot: $ProjectRoot"
    exit 1
}

Set-Location $ProjectRoot

Write-LogLine "Inicio mantenimiento expediente vivo"
Write-LogLine "ProjectRoot=$ProjectRoot"
Write-LogLine "DataDir=$DataDir"
Write-LogLine "Python=$Python"
Write-LogLine "Config=$Config"

$ExitCode = 0

$Code = Run-Step "export_client_context_from_index" {
    & $Python ".\scripts\export_client_context_from_index.py" --config $Config
}
if ($Code -ne 0) { $ExitCode = $Code }

$Code = Run-Step "hydrate_client_md_batch" {
    & $Python ".\scripts\hydrate_client_md_batch.py" `
        --config $Config `
        --write `
        --whitelist $ClientWhitelist `
        --blacklist $ClientBlacklist `
        --limit 100 `
        --min-documents 1
}
if ($Code -ne 0) { $ExitCode = $Code }

$Code = Run-Step "hydrate_expediente_md_batch" {
    & $Python ".\scripts\hydrate_expediente_md_batch.py" `
        --config $Config `
        --write `
        --whitelist $ExpedienteWhitelist `
        --limit 100
}
if ($Code -ne 0) { $ExitCode = $Code }

$Code = Run-Step "build_live_expedientes_index" {
    & $Python ".\scripts\build_live_expedientes_index.py" `
        --config $Config `
        --whitelist $ExpedienteWhitelist `
        --output $LiveExpedientesIndex
}
if ($Code -ne 0) { $ExitCode = $Code }

$Code = Run-Step "build_deadline_candidates" {
    & $Python ".\scripts\build_deadline_candidates.py" `
        --config $Config `
        --whitelist $ExpedienteWhitelist `
        --output $DeadlineCandidates
}
if ($Code -ne 0) { $ExitCode = $Code }

if (Test-Path $ConfirmedDeadlinesWorking) {
    $Code = Run-Step "build_deadline_control_report" {
        & $Python ".\scripts\build_deadline_control_report.py" `
            --input $ConfirmedDeadlinesWorking `
            --output $DeadlineControlReport
    }
    if ($Code -ne 0) { $ExitCode = $Code }
} else {
    Write-LogLine "build_deadline_control_report omitido: no existe $ConfirmedDeadlinesWorking"
}

Write-LogLine "Fin mantenimiento expediente vivo exit=$ExitCode"
exit $ExitCode