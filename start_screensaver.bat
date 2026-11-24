@echo off
setlocal enabledelayedexpansion
title KURO // ANIME Screensaver Launcher
cd /d "%~dp0"

echo ======================================================================
echo   KURO // ANIME - Cinematic Ambient Screensaver
echo   Windows Multi-Monitor ^& Kiosk Launcher
echo ======================================================================
echo.

:: 1. Verify Python availability
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found on your system PATH!
    echo.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Handle CLI Commands
if /i "%~1"=="--pin" (
    echo Pinning Kuro Anime Screensaver to Windows Start ^& Desktop...
    python launcher.py pin
    pause
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="--install-startup" (
    echo Registering KuroAnime to Windows Startup folder...
    python launcher.py startup enable
    pause
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="--remove-startup" (
    echo Removing KuroAnime from Windows Startup folder...
    python launcher.py startup disable
    pause
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="--status" (
    python launcher.py status
    pause
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="--stop" (
    python launcher.py stop
    pause
    exit /b %ERRORLEVEL%
)

:: 3. Launch Screensaver
echo Initializing server backend and detecting monitors...
python launcher.py start %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ======================================================================
    echo   [LAUNCH FAILED] KuroAnime screensaver could not be started.
    echo   Please inspect kuro_server.log for detailed error diagnostics.
    echo ======================================================================
    echo.
    pause
    exit /b 1
)

echo.
echo KuroAnime Screensaver is active. (Press any key to exit this window)
timeout /t 3 >nul
exit /b 0
