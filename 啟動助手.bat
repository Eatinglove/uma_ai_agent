@echo off
title Uma MCTS Assistant
echo ============================================
echo   Start Uma Training Assistant
echo   (proxy + capture + web UI)
echo ============================================
echo.
echo NOTE: Start this BEFORE launching the game.
echo       Close this window when done (proxy will be restored).
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0python_app\start.ps1"
echo.
echo Stopped. Press any key to close...
pause >nul