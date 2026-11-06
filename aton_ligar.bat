@echo off
cd /d "%~dp0"
rem Liga pela tarefa agendada "AI Core Aton" (veja docs\CONFIGURACAO.md, seção 11); sem ela, abre direto, sem janela.
powershell -NoProfile -Command "$p = '%~dp0'.ToLower(); if (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($p + 'venv\scripts\python') -and $_.CommandLine -like '*assistente.py*' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo O Aton ja esta ligado.
) else (
  schtasks /run /tn "AI Core Aton" >nul 2>&1 || start "" "%~dp0venv\Scripts\pythonw.exe" assistente.py
  echo Ligando o Aton... (leva uns 20 segundos para carregar a voz)
)
timeout /t 3 >nul
