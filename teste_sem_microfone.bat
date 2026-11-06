@echo off
rem Teste rápido sem microfone: o Aton responde a uma frase escrita e fecha.
cd /d "%~dp0"
venv\Scripts\python.exe assistente.py --frase "que horas são"
pause
