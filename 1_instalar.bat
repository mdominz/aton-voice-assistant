@echo off
cd /d "%~dp0"
if not exist venv python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements_celular.txt
rem openwakeword sem dependências: senão ele instala o onnxruntime comum por cima do onnxruntime-gpu
venv\Scripts\python.exe -m pip install --no-deps openwakeword
venv\Scripts\python.exe -c "from openwakeword import utils; utils.download_models(model_names=['hey_jarvis'])"
rem config.json pessoal: nasce do exemplo (preencha os IDs do Spotify/Outlook e o rustdesk_id se for usar)
if not exist config.json copy config.exemplo.json config.json
pause
