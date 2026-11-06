@echo off
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*assistente.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Assistente encerrado.
ping -n 3 127.0.0.1 >nul
