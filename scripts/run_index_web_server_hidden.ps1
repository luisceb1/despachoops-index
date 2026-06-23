$ErrorActionPreference = "Stop"

$Root = "D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index"
$LogDir = "D:\DespachoOpsData\Index\logs"

$BootLog = Join-Path $LogDir "web_server_boot.log"
$OutLog  = Join-Path $LogDir "web_server.out.log"
$ErrLog  = Join-Path $LogDir "web_server.err.log"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Existing = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*despachoops_index.web.app*" }

if ($Existing) {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Server already running. PID(s): $($Existing.ProcessId -join ', ')" |
        Out-File $BootLog -Append -Encoding utf8
    exit 0
}

"==================================================" | Out-File $BootLog -Append -Encoding utf8
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START web server hidden" | Out-File $BootLog -Append -Encoding utf8
"Root: $Root" | Out-File $BootLog -Append -Encoding utf8

Start-Process `
    -FilePath "$Root\.venv\Scripts\python.exe" `
    -ArgumentList "-m despachoops_index.web.app --config config.yaml --host 0.0.0.0 --port 8765" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog

Start-Sleep -Seconds 2

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Start-Process issued" |
    Out-File $BootLog -Append -Encoding utf8
