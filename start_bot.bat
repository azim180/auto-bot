@echo off
setlocal
cd /d "%~dp0"
title Discord + iTunes Visual Bot
call "%~dp0find_python.bat"
if not defined PY (
    echo Python 3 was not found. Double-click install_requirements.bat first.
    pause
    exit /b 1
)
echo Starting Discord + iTunes Visual Bot...
%PY% bot.py %*
pause
