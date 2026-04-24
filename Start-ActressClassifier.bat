@echo off
setlocal

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-SearchRuntime.ps1" -Launch
if errorlevel 1 (
    echo.
    echo Startup failed. See the message above for details.
    pause
    exit /b 1
)

