$ErrorActionPreference = "Stop"

$TaskName = "DespachoOps-Index-Night"
$ProjectRoot = "C:\DespachoOps\despachoops-index"
$Script = Join-Path $ProjectRoot "scripts\run_worker.ps1"
$Schtasks = "C:\Windows\System32\schtasks.exe"

if (-not (Test-Path $Script)) {
    throw "No existe script worker: $Script"
}

if (-not (Test-Path $Schtasks)) {
    throw "No existe schtasks.exe en $Schtasks"
}

$Command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Script`""

Write-Host "Eliminando tarea previa si existe..."
& $Schtasks /Delete /TN $TaskName /F *> $null
# Ignoramos el resultado del borrado: si no existe, no pasa nada.
$global:LASTEXITCODE = 0

Write-Host "Creando tarea programada..."

& $Schtasks /Create `
    /TN $TaskName `
    /TR $Command `
    /SC MINUTE `
    /MO 10 `
    /ST 23:00 `
    /DU 08:00 `
    /RL HIGHEST `
    /F

if ($LASTEXITCODE -ne 0) {
    throw "Error creando tarea programada. ExitCode=$LASTEXITCODE"
}

Write-Host "Tarea instalada: $TaskName"
Write-Host "Script: $Script"
Write-Host "Inicio: 23:00"
Write-Host "Repetición: cada 10 minutos durante 8 horas"