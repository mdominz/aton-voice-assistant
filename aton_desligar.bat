@echo off
cd /d "%~dp0"
call "%~dp03_parar.bat" >nul
echo Aton DESLIGADO. Para ligar: aton_ligar.bat (ou ele liga sozinho ao entrar no Windows, se a tarefa estiver criada).
timeout /t 3 >nul
