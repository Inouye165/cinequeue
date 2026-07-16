@echo off
echo ========================================================
echo Starting Cinequeue Backend (Port 8081) and Frontend...
echo ========================================================

:: Start Backend in a new window
echo Launching Backend server...
start "Cinequeue Backend" cmd /k "cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8081"

:: Start Frontend in a new window
echo Launching Frontend server...
start "Cinequeue Frontend" cmd /k "cd frontend && npm run dev"

echo Both servers launching. Close the individual command windows to stop them.
