# Helper script to run tests and create PR
$ErrorActionPreference = "Stop"

Write-Host "=== Running Backend Tests ===" -ForegroundColor Blue
cd backend
.venv\Scripts\pytest
if ($LASTEXITCODE -ne 0) {
    Write-Host "Backend tests failed!" -ForegroundColor Red
    exit 1
}

Write-Host "=== Running Frontend Tests ===" -ForegroundColor Blue
cd ../frontend
npm test
if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend tests failed!" -ForegroundColor Red
    exit 1
}

cd ..
Write-Host "=== Creating Branch & Committing ===" -ForegroundColor Blue
# Checkout or create the feature branch
$branch = "feature/queue-sort-following"
$existingBranch = git branch --list $branch
if (-not $existingBranch) {
    git checkout -b $branch
} else {
    git checkout $branch
}
git add .
git commit -m "feat: add YouTube movie trailers, sort queue chronologically, add Following tab, and fix Firebase configuration"

Write-Host "=== Pushing to GitHub ===" -ForegroundColor Blue
git push -u origin $branch

Write-Host "=== Creating Pull Request ===" -ForegroundColor Blue
gh pr create --title "feat: Firebase config, YouTube trailers, chronological queue sorting & Following status" --body "### Summary of Changes

This Pull Request bundles the implementation of several key improvements:

1. **Firebase Web Configuration Fix**
   - Added missing Firebase Web configuration to \`cloudbuild.yaml\` to ensure the production environment loads correct secret mappings and config values.

2. **YouTube Movie Trailers Integration**
   - Implemented fetching of official movie/show trailers via TMDB API.
   - Added an expandable miniature YouTube trailer player box directly on the details modal.

3. **Queue Sorting & Status Management**
   - Sorted the **My Queue** list chronologically by release date ascending.
   - Introduced a new **Following** status and tab to track items currently being watched.
   - Refined the date countdown labels (displaying months, weeks, and days, and hiding badges for already-released items).

4. **Testing & Regression Validation**
   - Added unit tests for date countdown logic in \`backend/tests/test_models.py\`.
   - Added route validation tests in \`backend/tests/test_api.py\` and repository tests in \`backend/tests/test_repository.py\`."
