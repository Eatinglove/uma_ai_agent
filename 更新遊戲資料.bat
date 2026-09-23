@echo off
title Update Game Data
echo ============================================
echo   Update Support Card / Uma Data
echo   (re-export from game master.mdb)
echo ============================================
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0python_app\tools\refresh_data.ps1"
echo.
echo Done! Press any key to close...
pause >nul