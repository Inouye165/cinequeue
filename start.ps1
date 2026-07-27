$rootDir = $PSScriptRoot
if (-not $rootDir) { $rootDir = (Get-Location).Path }

function Stop-CinequeueServerOnPort {
    param (
        [int]$Port,
        [string]$ServerName,
        [string[]]$Keywords
    )

    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        return $true
    }

    $allSuccess = $true
    foreach ($conn in $conns) {
        $targetPid = $conn.OwningProcess
        if ($targetPid -and $targetPid -gt 4) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $targetPid" -ErrorAction SilentlyContinue
            if ($proc) {
                $cmdLine = $proc.CommandLine
                $isCinequeue = $false

                if ($cmdLine) {
                    foreach ($kw in $Keywords) {
                        if ($cmdLine.ToLower().Contains($kw.ToLower())) {
                            $isCinequeue = $true
                            break
                        }
                    }
                }

                if ($isCinequeue) {
                    Write-Host "[CineQueue] Found existing CineQueue $ServerName (PID: $targetPid, Port: $Port). Closing..." -ForegroundColor Yellow
                    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 1
                } else {
                    Write-Host "========================================================" -ForegroundColor Red
                    Write-Host "[SAFETY ABORT] Port $Port ($ServerName) is in use by a NON-CineQueue process!" -ForegroundColor Red
                    Write-Host "PID: $targetPid" -ForegroundColor Red
                    Write-Host "Process: $($proc.Name)" -ForegroundColor Red
                    Write-Host "Command: $cmdLine" -ForegroundColor Red
                    Write-Host "CineQueue will NOT stop this process to prevent interfering with your running applications." -ForegroundColor Red
                    Write-Host "========================================================" -ForegroundColor Red
                    $allSuccess = $false
                }
            }
        }
    }

    return $allSuccess
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " CineQueue Dev Startup -- Checking Active Servers..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$backendSafe = Stop-CinequeueServerOnPort -Port 8081 -ServerName "Backend" -Keywords @("app.main:app", "cinequeue\backend", "$rootDir\backend", "cinequeue")
$frontendSafe = Stop-CinequeueServerOnPort -Port 5180 -ServerName "Frontend" -Keywords @("vite", "cinequeue\frontend", "$rootDir\frontend", "cinequeue")

if (-not $backendSafe -or -not $frontendSafe) {
    Write-Host "[CineQueue] Startup aborted to protect non-CineQueue applications." -ForegroundColor Red
    exit 1
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Launching CineQueue Backend (Port 8081) and Frontend (Port 5180)..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# Start Backend in a new window
Write-Host "Launching Backend server (http://localhost:8081)..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k title Cinequeue Backend (8081) & cd /d `"$rootDir\backend`" & .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8081"

# Start Frontend in a new window
Write-Host "Launching Frontend server (http://localhost:5180)..." -ForegroundColor Yellow
Start-Process cmd.exe -ArgumentList "/k title Cinequeue Frontend (5180) & cd /d `"$rootDir\frontend`" & npm run dev"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Both servers launching in separate terminal windows." -ForegroundColor Green
Write-Host " Close the spawned windows anytime to stop the servers." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
