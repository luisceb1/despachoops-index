# Registra tarea que ejecuta el worker cada 10 min; el script solo trabaja 23:00–06:00.
# Ejecutar PowerShell como Administrador.

$TaskName = "DespachoOps-Index-Night"
$ProjectRoot = "C:\ProyectosCoding\DespachoOps - Index"
$Script = Join-Path $ProjectRoot "scripts\run_worker.ps1"

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""

# Repetir cada 10 min entre 23:00 y 06:59 (el filtro real lo hace Python)
$Trigger = New-ScheduledTaskTrigger -Daily -At "23:00"
$Trigger.RepetitionInterval = (New-TimeSpan -Minutes 10)
$Trigger.RepetitionDuration = (New-TimeSpan -Hours 8)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "Tarea registrada: $TaskName"
Write-Host "Comprueba rutas en $Script y config.yaml"
