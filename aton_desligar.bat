@echo off
cd /d "%~dp0"
call "%~dp03_parar.bat" >nul
echo Aton DESLIGADO. Para ligar: atalho "Aton - Ligar" (ou ele liga sozinho ao entrar no Windows).
timeout /t 3 >nul
