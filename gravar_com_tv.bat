@echo off
chcp 65001 >nul
title Gravar com a TV ligada (Aton)
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0gravar_voz.py" --tv
