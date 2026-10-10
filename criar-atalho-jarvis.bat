@echo off
setlocal
title JARVIS - criar atalho
cd /d "%~dp0"
if not exist "main.py" if exist "Mark-LV-main\main.py" cd /d "%~dp0Mark-LV-main"
if not exist "main.py" (
    echo [ERRO] main.py nao encontrado. Coloque este arquivo na pasta do JARVIS
    echo        ^(a que contem main.py^) e rode de novo.
    pause & exit /b 1
)

rem ---- Python sem janela de terminal (pythonw.exe) ----
set "PYW="
if exist ".venv\Scripts\pythonw.exe" set "PYW=%CD%\.venv\Scripts\pythonw.exe"
if not defined PYW (
    for /f "delims=" %%i in ('py -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
)
if not defined PYW (
    for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
)
if not defined PYW (
    echo [ERRO] Python nao encontrado.
    pause & exit /b 1
)
if not exist "%PYW%" (
    echo [ERRO] pythonw.exe nao encontrado em "%PYW%".
    pause & exit /b 1
)

set "PROJ=%CD%"
set "ICON=%CD%\config\jarvis.ico"
if not exist "%ICON%" set "ICON=%PYW%"

echo Pasta do JARVIS : %CD%
echo Python          : %PYW%
echo Icone           : %ICON%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$dirs = @([Environment]::GetFolderPath('Desktop'), $env:PROJ);" ^
  "foreach ($d in $dirs) {" ^
  "  $s = $ws.CreateShortcut((Join-Path $d 'JARVIS.lnk'));" ^
  "  $s.TargetPath = $env:PYW;" ^
  "  $s.Arguments = 'main.py';" ^
  "  $s.WorkingDirectory = $env:PROJ;" ^
  "  $s.IconLocation = $env:ICON + ',0';" ^
  "  $s.Description = 'MARK LV - JARVIS';" ^
  "  $s.WindowStyle = 1;" ^
  "  $s.Save();" ^
  "  Write-Host ('Atalho criado: ' + (Join-Path $d 'JARVIS.lnk'))" ^
  "}"

echo.
echo Pronto. Na area de trabalho ha um icone JARVIS: dois cliques abrem o
echo assistente sem janela de terminal. Para fixar na barra de tarefas,
echo clique com o botao direito no atalho ^> Mostrar mais opcoes ^> Fixar na
echo barra de tarefas. Se precisar ver mensagens de erro, use iniciar-jarvis.bat
echo ou "py main.py" no terminal.
pause
