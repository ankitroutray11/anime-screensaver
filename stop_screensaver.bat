@echo off
setlocal enabledelayedexpansion
title Stop KuroAnime Screensaver
cd /d "%~dp0"

echo ======================================================================
echo   Stopping KURO // ANIME Screensaver ^& Background Workers...
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python launcher.py stop
) else (
    echo [Notice] Python not found on PATH. Attempting native process cleanup...
    powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*server.py*' -or $_.CommandLine -like '*launcher.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Stopped process ' + $_.ProcessId) }"
)

echo.
echo Screensaver stopped cleanly.
timeout /t 2 >nul
exit /b 0
