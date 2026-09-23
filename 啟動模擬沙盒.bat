@echo off
title Aoharu Sim Sandbox
echo ============================================
echo   Aoharu Sim Sandbox (web)
echo ============================================
echo.
echo Opens http://127.0.0.1:5000/sim in your browser.
echo Close this window when done.
echo.
echo NOTE: For "live" mode, run the main launcher ("start assistant" bat)
echo       once first so the watcher produces current_turn.json.
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0python_app\sim_web.ps1" %*
echo.
echo Stopped. Press any key to close...
pause >nul