@echo off
chcp 65001 >nul
title Gravar a sua voz para o Aton
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0gravar_voz.py"
