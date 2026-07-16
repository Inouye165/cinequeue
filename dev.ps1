Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Cinequeue Backend (Port 8081) and Frontend..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# Start Backend in a new window
Write-Host "Launching Backend server..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8081"

# Start Frontend in a new window
Write-Host "Launching Frontend server..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k cd frontend && npm run dev"

Write-Host "Both servers launching. Close the individual command windows to stop them." -ForegroundColor Green
