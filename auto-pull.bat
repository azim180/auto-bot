@echo off
setlocal
cd /d "%~dp0"
title Git auto-pull
call "%~dp0find_python.bat"
if not defined PY (
    echo Python 3 was not found. Double-click install_requirements.bat first.
    pause
    exit /b 1
)
%PY% auto-pull.py
pause
