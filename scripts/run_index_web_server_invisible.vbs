Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""D:\Cebrian y Fraile Abogados\DespachoOps\despachoops-index\scripts\run_index_web_server_hidden.ps1""", 0, False
