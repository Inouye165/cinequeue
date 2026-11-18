# Delegates to dev.ps1 so backend (8081) and frontend (5180) ports stay consistent.
& (Join-Path $PSScriptRoot "dev.ps1")
exit $LASTEXITCODE
