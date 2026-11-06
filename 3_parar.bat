@echo off
rem Para SÓ o Aton desta pasta (outros programas Python e outras cópias do Aton não são tocados).
powershell -NoProfile -Command "$p = '%~dp0'.ToLower(); Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($p + 'venv\scripts\python') -and $_.CommandLine -like '*assistente.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Assistente encerrado.
ping -n 3 127.0.0.1 >nul
