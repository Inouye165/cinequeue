# CineQueue Workspace Rules

## Mandatory Port Rule
- **NEVER use port 5173** for Vite or any server in this workspace. Port 5173 is reserved for the user's machine learning / sheep dog simulation app.
- **ALWAYS use port 5180** for the CineQueue frontend Vite server (`npm run dev` or `npx vite --port 5180`).
