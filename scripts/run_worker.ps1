# DespachoOps Index — ciclo nocturno: worker + OCR enrich + contexto cliente + markdown + dashboard histórico + latest
$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"
$DataDir = "D:\DespachoOpsData\Index"
$ReportsDir = "D:\Cebrian y Fraile Abogados\Index\reports"
$LatestDir = "D:\Cebrian y Fraile Abogados\Index\latest"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $DataDir "logs"
$LogFile = Join-Path $LogDir "run_worker_$Stamp.log"

$env:PYTHONPATH = "$ProjectRoot\src"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"
$Config = Join-Path $ProjectRoot "config.yaml"

$PrioritizeOcr = Join-Path $ProjectRoot "scripts\prioritize_ocr_queue.py"
$OcrEnrich = Join-Path $ProjectRoot "scripts\enrich_ocr_documents.py"
$ClientContextExport = Join-Path $ProjectRoot "scripts\export_client_context_from_index.py"
$MarkdownHotfix = Join-Path $ProjectRoot "scripts\index_markdown_hotfix.py"

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
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-LogLine "$Name falló con código $LASTEXITCODE"
        return $LASTEXITCODE
    }
    return 0
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
New-Item -ItemType Directory -Force -Path $LatestDir | Out-Null

if (-not (Test-Path $ProjectRoot)) {
    Write-Host "No existe ProjectRoot: $ProjectRoot"
    exit 1
}

if (-not (Test-Path $Config)) {
    Write-Host "No existe config.yaml: $Config"
    exit 1
}

Set-Location $ProjectRoot

Write-LogLine "Inicio run_worker (DespachoOps Index)"
Write-LogLine "ProjectRoot=$ProjectRoot"
Write-LogLine "DataDir=$DataDir"
Write-LogLine "ReportsDir=$ReportsDir"
Write-LogLine "LatestDir=$LatestDir"
Write-LogLine "Python=$Python"
Write-LogLine "Config=$Config"

$ExitCode = 0

$Code = Run-Step "init (data_dir, logs, OCR, reports, latest)" {
    & $Python -m despachoops_index.cli --config $Config init | ForEach-Object {
        Write-LogLine $_
    }
}
if ($Code -ne 0) { $ExitCode = $Code }

if (Test-Path $PrioritizeOcr) {
    $Code = Run-Step "prioritize_ocr_queue" {
        & $Python $PrioritizeOcr --config $Config | ForEach-Object {
            Write-LogLine $_
        }
    }
    if ($Code -ne 0) { $ExitCode = $Code }
} else {
    Write-LogLine "prioritize_ocr_queue omitido: no existe $PrioritizeOcr"
}

$Code = Run-Step "worker --once" {
    & $Python -m despachoops_index.cli --config $Config worker --once
}
if ($Code -ne 0) { $ExitCode = $Code }

if (Test-Path $OcrEnrich) {
    $Code = Run-Step "enrich_ocr_documents" {
        & $Python $OcrEnrich --config $Config | ForEach-Object {
            Write-LogLine $_
        }
    }
    if ($Code -ne 0) { $ExitCode = $Code }
} else {
    Write-LogLine "enrich_ocr_documents omitido: no existe $OcrEnrich"
}

if (Test-Path $ClientContextExport) {
    $Code = Run-Step "export_client_context_from_index" {
        & $Python $ClientContextExport --config $Config | ForEach-Object {
            Write-LogLine $_
        }
    }
    if ($Code -ne 0) { $ExitCode = $Code }
} else {
    Write-LogLine "export_client_context_from_index omitido: no existe $ClientContextExport"
}

# Markdown cliente/expediente: hotfix aislado.
# No toca scan_root. Solo lee .md/.markdown y escribe en SQLite/data_dir/client_context.
if (Test-Path $MarkdownHotfix) {
    $Code = Run-Step "index_markdown_hotfix" {
        & $Python $MarkdownHotfix --config $Config --force | ForEach-Object {
            Write-LogLine $_
        }
    }
    if ($Code -ne 0) { $ExitCode = $Code }
} else {
    Write-LogLine "index_markdown_hotfix omitido: no existe $MarkdownHotfix"
}

$Code = Run-Step "dashboard (reports con timestamp) + publish-latest" {
    & $Python -m despachoops_index.cli --config $Config dashboard --publish-latest | ForEach-Object {
        Write-LogLine $_
    }
}
if ($Code -ne 0) {
    $ExitCode = $Code
} else {
    Write-LogLine "latest publicado en $LatestDir\index_dashboard.xlsx"
}

Write-LogLine "Fin run_worker (exit=$ExitCode)"
exit $ExitCode