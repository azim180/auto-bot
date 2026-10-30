@echo off
setlocal
cd /d "%~dp0"
title Install bot requirements
echo ============================================================
echo  Installing everything the Visual Bot needs
echo ============================================================
echo.

call "%~dp0find_python.bat"
if defined PY goto :have_python

echo Python 3 was not found on this PC.
where winget >nul 2>&1
if errorlevel 1 goto :no_python
echo Installing Python 3.12 with winget - this can take a few minutes...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
call "%~dp0find_python.bat"
if not defined PY goto :no_python

:have_python
echo Using Python:
%PY% --version
echo.

rem pip runs as "python -m pip", so it works even when pip is not on PATH
%PY% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip is missing - adding it...
    %PY% -m ensurepip --upgrade
)
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
%PY% -c "import pyautogui, cv2, numpy, PIL, pyperclip; print('[OK] pyautogui, opencv, numpy, pillow and pyperclip all work.')"
if errorlevel 1 goto :failed

echo.
echo All packages installed! You can now double-click start_bot.bat to run the bot.
pause
exit /b 0

:no_python
echo.
echo Could not install Python automatically.
echo Install Python 3 from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" on the first screen, then run this file again.
pause
exit /b 1

:failed
echo.
echo [ERROR] Installing the packages failed - read the messages above.
echo Check your internet connection and run this file again.
pause
exit /b 1
