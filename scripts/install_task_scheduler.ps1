$TaskName = "DespachoOps-Index-Night"
$ProjectRoot = "C:\DespachoOps\despachoops-index"
$Script = Join-Path $ProjectRoot "scripts\run_worker.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -Daily -At "23:00"
$Trigger.RepetitionInterval = (New-TimeSpan -Minutes 10)
$Trigger.RepetitionDuration = (New-TimeSpan -Hours 8)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "Tarea: $TaskName"
