@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*assistente.py*' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo O Aton ja esta ligado.
) else (
  schtasks /run /tn "AI Core Aton" >nul
  echo Ligando o Aton... (leva uns 20 segundos para carregar a voz)
)
timeout /t 3 >nul
