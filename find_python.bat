@echo off
rem Sets PY to a command that runs Python 3, or leaves PY undefined when there is none.
rem Called (not run) by install_requirements.bat, start_bot.bat and auto-pull.bat.
set "PY="

rem 1. The Python launcher from python.org - works even when python is not on PATH
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto :eof
)

rem 2. python on PATH. The Microsoft Store placeholder fails this check and is skipped.
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto :eof
)

rem 3. The usual install folders, for when PATH was not updated (e.g. right after installing)
if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" (
    set PY="%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" -3
    goto :eof
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do (
    if exist "%%~fD\python.exe" set PY="%%~fD\python.exe"
)
goto :eof
