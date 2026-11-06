@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando o Aton (5 a 15 minutos; baixa cerca de 2,5 GB na primeira vez)...
echo.
rem Python 3.13 (algumas bibliotecas ainda não existem para o 3.14)
if not exist venv (
  py -3.13 -m venv venv || goto :sem_python
)
venv\Scripts\python.exe -m pip install --upgrade pip || goto :erro
venv\Scripts\python.exe -m pip install -r requirements.txt || goto :erro
venv\Scripts\python.exe -m pip install -r requirements_celular.txt || goto :erro
venv\Scripts\python.exe -c "from openwakeword import utils; utils.download_models(model_names=['hey_jarvis'])" || goto :erro
rem config.json pessoal: nasce do exemplo (depois preencha cidade, microfone e, se for usar, os IDs do Spotify/Outlook)
if not exist config.json copy config.exemplo.json config.json >nul
echo.
echo Pronto! Agora edite o config.json e rode teste_sem_microfone.bat para um teste rapido.
pause
exit /b 0

:sem_python
echo.
echo ERRO: Python 3.13 nao encontrado. Instale a versao 3.13 mais recente em https://www.python.org/downloads/windows/
echo (marque "Add python.exe to PATH") e rode este arquivo de novo.
pause
exit /b 1

:erro
echo.
echo ERRO: a instalacao falhou (veja a mensagem acima). Nada foi configurado; corrija e rode de novo.
pause
exit /b 1
