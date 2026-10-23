# CineQueue Workspace Rules

## Mandatory Port Rule
- **NEVER use port 5173** for Vite or any server in this workspace. Port 5173 is reserved for the user's machine learning / sheep dog simulation app.
- **ALWAYS use port 5180** for the CineQueue frontend Vite server (`npm run dev` or `npx vite --port 5180`).

## Local Server Rule
- **ALWAYS restart the local server** whenever code changes are made.

## Git & Branching Workflow Rules
1. **Pre-Work Verification (Check for Uncommitted Changes):**
   - Before starting any new task or making code changes, inspect the repository state (`git status`).
   - If there are **uncommitted changes** from previous work, **STOP** and advise the user immediately.
   - Explicitly ask the user to confirm whether to commit the pending changes locally and start fresh on a new branch before proceeding.
2. **Branch Creation Before Work:**
   - **ALWAYS create and switch to a new descriptive branch** (e.g., `feat/...`, `fix/...`, `chore/...`) before making any code changes for a new task.
3. **Commit Locally After Completion (Do NOT Push Automatically):**
   - **ALWAYS stage and commit changes locally** with a clear, descriptive commit message once the requested work is complete and verified, leaving the working tree clean so a new branch can be started next time.
   - **NEVER push commits to GitHub (`git push`) automatically** unless the user explicitly asks to push, as pushing triggers the CI/deployment pipeline.
