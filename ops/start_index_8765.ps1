$ErrorActionPreference = "Stop"

$IndexRoot = "D:\Cebrian y Fraile Abogados\Index"
$AppDir = "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $AppDir "logs"
$LogFile = Join-Path $LogDir "index_web_8765.log"

New-Item -ItemType Directory -Force $LogDir | Out-Null

if (-not (Test-Path $Python)) {
    throw "No existe Python de Index: $Python"
}

Set-Location $IndexRoot

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Arrancando Index en 0.0.0.0:8765 sobre $IndexRoot" | Out-File -FilePath $LogFile -Encoding utf8 -Append

& $Python -m http.server 8765 --bind 0.0.0.0 *>> $LogFile
