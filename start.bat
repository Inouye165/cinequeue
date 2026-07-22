@echo off
set "ROOT_DIR=%~dp0"
echo ========================================================
echo  Starting Cinequeue Backend (Port 8081) and Frontend...
echo ========================================================

:: Start Backend in a new window
echo Launching Backend server (http://localhost:8081)...
start "Cinequeue Backend (8081)" cmd /k "cd /d "%ROOT_DIR%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8081"

:: Start Frontend in a new window
echo Launching Frontend server...
start "Cinequeue Frontend" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev"

echo ========================================================
echo Both servers launching. Close individual windows to stop.
echo ========================================================
