@echo off
chcp 65001 >nul
title Treinar o detector do Aton
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0treinar_aton.py"
echo.
echo Pronto. Reinicie o Aton (3_parar.bat e depois aton_ligar.bat) para usar o modelo novo.
pause
