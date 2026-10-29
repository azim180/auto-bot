@echo off
setlocal
rem ============================================================
rem  auto-pull.bat  -  keeps this folder in sync with GitHub.
rem  Drop it in the root of your cloned repo and double-click.
rem  Close the window to stop.
rem ============================================================

set INTERVAL=30

cd /d "%~dp0"
title Git auto-pull  [%CD%]

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo No git repo found in: %CD%
    echo Make sure Git is installed and this file is inside your cloned repo.
    pause
    exit /b
)

set UPSTREAM=
for /f "delims=" %%u in ('git rev-parse --abbrev-ref @{u} 2^>nul') do set UPSTREAM=%%u
if not defined UPSTREAM (
    echo Your current branch has no remote tracking branch.
    echo Run this once to fix it:
    echo   git checkout -b main origin/main
    pause
    exit /b
)

findstr /l /x /c:"%~nx0" ".git\info\exclude" >nul 2>&1 || echo %~nx0>>".git\info\exclude"

echo ============================================================
echo  Folder  : %CD%
echo  Tracking: %UPSTREAM%
echo  Interval: every %INTERVAL% seconds
echo  Minimize this window to keep it running, close it to stop.
echo ============================================================
echo.

:loop
git fetch --quiet 2>nul
set BEHIND=0
for /f %%n in ('git rev-list --count HEAD..@{u} 2^>nul') do set BEHIND=%%n
if "%BEHIND%"=="0" (
    echo [%TIME:~0,8%] Up to date.
) else (
    echo [%TIME:~0,8%] %BEHIND% new commit(s) found - pulling...
    git pull --ff-only
    echo.
)
powershell -Command "Start-Sleep -Seconds %INTERVAL%"
goto loop
