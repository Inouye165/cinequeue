# Helper script to verify tests and explicitly confirm pushing the current branch.
$ErrorActionPreference = "Stop"

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -eq "main" -or $branch -eq "master" -or -not $branch) {
    Write-Host "Refusing to push protected or detached branch '$branch'. Check out a feature branch first." -ForegroundColor Red
    exit 1
}

Write-Host "=== Running Backend Tests ===" -ForegroundColor Blue
Push-Location backend
try {
    $env:PYTHONPATH = "."
    .venv\Scripts\python.exe -m pytest tests -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Backend tests failed!" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "=== Running Frontend Build & Tests ===" -ForegroundColor Blue
Push-Location frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { exit 1 }
    npx vitest run
    if ($LASTEXITCODE -ne 0) { exit 1 }
} finally {
    Pop-Location
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Host "Working tree has uncommitted changes. Commit them before pushing:" -ForegroundColor Yellow
    git status --short
    exit 1
}

$confirm = Read-Host "Push branch '$branch' to origin and create/update PR? [y/N]"
if ($confirm -notin @("y", "Y", "yes", "YES")) {
    Write-Host "Aborted before pushing." -ForegroundColor Yellow
    exit 0
}

git push -u origin $branch
gh pr create --fill
