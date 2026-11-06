@echo off
cd /d "%~dp0"
if exist "pausado.flag" (
  del "pausado.flag"
  echo Aton RETOMADO: escutando "Aton" de novo.
) else (
  echo pausado > "pausado.flag"
  echo Aton PAUSADO: nao escuta nem fala sozinho. Clique de novo para retomar.
)
timeout /t 2 >nul
