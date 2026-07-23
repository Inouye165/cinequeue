$rootDir = $PSScriptRoot
if (-not $rootDir) { $rootDir = (Get-Location).Path }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Starting Cinequeue Backend (Port 8081) & Frontend..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# Start Backend in a new window
Write-Host "Launching Backend server (http://localhost:8081)..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k ""cd /d `"$rootDir\backend`" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8081"""

# Start Frontend in a new window
Write-Host "Launching Frontend server..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k ""cd /d `"$rootDir\frontend`" && npm run dev"""

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Both servers launching in separate terminal windows." -ForegroundColor Green
Write-Host " Close the spawned windows anytime to stop the servers." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
