# Cinequeue

Personal movie and TV tracker with release countdowns, where-to-watch info, reviews, and news.

## Stack

- **Frontend:** React + TypeScript (Vite), Google Firebase Authentication (Client SDK)
- **Backend:** Python FastAPI, Google Firebase Admin SDK (Session Cookie Verification)
- **Data:** TMDB API + Google News RSS + Google Cloud Firestore (Watchlist Persistence)
- **Deploy:** Google Cloud Run (Docker) via GitHub CI/CD

## Authentication & Authorization

### On-device-first collection

The collection opens from IndexedDB without waiting for Firebase or a backend
session. Queue, monitoring, library and rating edits are saved on the device first.
Google sign-in enables background sync; discovery, fresh availability and AI
features still require an online cloud session.

- Each account has separate movie records, pending operations and sync cursors.
  Switching accounts cancels in-flight sync. The server rejects sync requests
  whose expected owner differs from the authenticated session.
- An unavailable or expired cloud session does not remove the saved workspace.
  **Sign in to sync** reconnects it; **Use device-only workspace** or explicit
  sign-out switches to a separate guest collection without deleting account data.
- Guest changes remain on the device and are not automatically uploaded or merged
  into an account. Signing in opens that account's separate workspace.
- Saved titles have basic offline details; full details are cached after a successful
  online view. Images, trailers and other external content may be unavailable offline.
- Local workspace selection is not authentication and does not grant cloud or admin
  access. Anyone with access to the same browser profile can access its saved local
  data; use separate OS/browser profiles on shared devices.
- Existing local records migrate without clearing storage. Legacy queued operations
  with no provable owner are retained as failed and excluded from automatic sync.
  Data overwritten by older versions cannot be reconstructed by the migration.

### Safe synchronization and recovery

- Cloud sync uses atomic compare-and-write revisions. Concurrent edits are not
  silently overwritten: open the account menu and choose **Keep device version**
  or **Keep cloud version**. Both displaced versions are retained in recovery data
  included in workspace backups.
- Durable operation receipts make retries idempotent, including a lost response
  after the server commits. Full authoritative snapshots propagate removals and
  cleared ratings without overwriting pending local edits.
- One worker runs per account across tabs (Web Locks, with an IndexedDB lease
  fallback). It drains edits made during sync, persists attempts, and retries
  transient failures with bounded exponential backoff. Rejected operations remain
  visible with their reasons; **Retry rejected changes** retries them explicitly.
- The status bar distinguishes pending work, conflicts, authentication failures
  and sync errors. It says **Synced** only after a valid pull and an empty outbox
  with no unresolved conflicts.
- In the account menu, **Protect device storage** requests persistent browser
  storage and shows usage/quota. A denied or unsupported request is shown honestly.
  Persistence is not a backup and does not protect against clearing site data.
- **Export workspace backup** downloads a private, versioned JSON file containing
  only the selected workspace, its immutable pending operations and recovery
  versions. Export and restore share a 25 MB limit; oversized exports report an
  error rather than generating a file that cannot be restored.
  **Restore workspace backup** validates ownership, structure and size
  and restores atomically into an empty workspace. It never
  overwrites another account or an existing collection. User data is restored;
  online detail caches are refreshed separately. Restored cloud data is checked
  against current revisions before upload.
- Clearing a workspace requires an explicit data-loss acknowledgement and is
  serialized against sync. Export first, especially for guest or unsynced data.

Browser storage is not a backup: browser eviction or clearing site data can remove
local collections and recovery versions. Keep exported backups outside the browser.
Legacy clients remain API-compatible but do not have v2 conflict protection;
update all devices before relying on cross-device conflict resolution.

Cinequeue features production-grade per-user authentication and authorization using Firebase Authentication.

### Key Security Design Patterns
- **Token Exchange:** The frontend exchanges a short-lived Firebase ID token for a secure backend-managed session cookie.
- **Secure Cookies:** In production, session cookies are configured with `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, and use the `__Host-` prefix (no `Domain` attribute) to protect against XSS and session hijacking.
- **CSRF Protection:** Crucial mutation endpoints (session login, logout, watchlist writes) validate a stateful CSRF token set by the backend via a separate cookie and validated matching custom headers.
- **User Scoping:** The watchlist database (both SQLite and Firestore) scopes records under the verified user's `uid`. User A cannot read or mutate User B's watchlist.
- **Fail Closed:** The application configuration defaults to failing closed. Any missing environment configuration in production throws immediate validation errors.

## Environment Variables

| Variable | Description | Default | Required in Prod |
| :--- | :--- | :--- | :--- |
| `TMDB_API_KEY` | TMDB developer API key for movie/TV database queries | None | **Yes** |
| `WATCHLIST_BACKEND` | Database backend: `sqlite` or `firestore` | `sqlite` | **Yes** (set to `firestore`) |
| `AUTH_ENABLED` | Set `true` to enable Firebase Auth and per-user database scoping | `false` | **Yes** (set to `true`) |
| `AUTH_MODE` | Authorization mode: `allowlist` (only authorized emails) or `all` | `allowlist` | **Yes** |
| `AUTH_ALLOWED_EMAILS` | Comma-separated allowlist of Google emails (e.g. `inouye165@gmail.com`) | None | **Yes** (when `AUTH_MODE=allowlist`) |
| `AUTH_ALLOWED_ORIGINS` | Comma-separated allowed frontend Origins for CORS and CSRF | None | **Yes** (when `AUTH_ENABLED=true`) |
| `SESSION_COOKIE_SECURE` | Set `true` to mandate HTTPS and use `__Host-` session cookies | `false` | **Yes** (when `AUTH_ENABLED=true`) |
| `FIREBASE_PROJECT_ID` | GCP/Firebase project ID (`cinequeue-inouye-2026`) | None | **Yes** (when `AUTH_ENABLED=true`) |

## Local Development

### 1. Get a TMDB API key

Create a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).

### 2. Configure environment

Create a `.env` file in the root workspace (or copy `.env.example`). Set:
- `TMDB_API_KEY=your_tmdb_key_here`
- `AUTH_ENABLED=false` (this enables local SQLite mock mode automatically bypasses Google sign-in and authenticates as `Local Developer` with local database storage).

### 3. One-Command Startup (Recommended)

You can start both backend and frontend servers with a single command:

#### Option A: Unified Terminal (using `concurrently`)
First, install root dependencies (if not already done):
```bash
npm install
```
Then start both servers in the same terminal:
```bash
npm run dev
```

#### Option B: Separate Windows (using helper scripts)
If you prefer logs in separate terminal windows, run the batch script (on Windows):
```cmd
dev.bat
```
Or run the PowerShell script:
```powershell
.\dev.ps1
```

### 4. Manual Backend development


```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

### 4. Frontend development (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5180](http://localhost:5180). The Vite dev server proxies `/api` to port 8081.

### 5. Local testing

**Backend tests:**
```bash
cd backend
pytest tests/ -v
```

**Frontend tests:**
```bash
cd frontend
npm run test
```

**Browser regressions (production PWA, offline reload, account isolation, backup/restore,
conflict recovery and live updates across tabs):**
```powershell
cd frontend
npx playwright install chromium
npm run test:e2e
```

Both Cloud Build pipelines run unit/component tests and browser regressions before
deployment. Browser tests use isolated profiles and an unavailable cloud API; they
do not need Firebase credentials or touch live account data.

### 6. Local Docker build and run

```bash
docker build -t cinequeue .
docker run -p 8080:8080 -e TMDB_API_KEY=your_key_here cinequeue
```

Open [http://localhost:8080](http://localhost:8080).

## Google Cloud Deployment

### Required Google Cloud Services

- **Cloud Run:** Serverless container runtime
- **Cloud Build:** CI/CD pipeline
- **Artifact Registry:** Docker_image storage
- **Secret Manager:** TMDB API key storage

### Configuration Details

- **Project ID:** `cinequeue-inouye-2026`
- **Region:** `us-west1`
- **Cloud Run service:** `cinequeue`
- **Artifact Registry path:** `us-west1-docker.pkg.dev/cinequeue-inouye-2026/cinequeue/cinequeue:$SHORT_SHA`
- **Secret Manager secret:** `tmdb-api-key`
- **Runtime service account:** `cinequeue-runner@cinequeue-inouye-2026.iam.gserviceaccount.com`

### Important: Temporary SQLite Storage

**SQLite data is temporary on Cloud Run.** Cloud Run containers are ephemeral - the SQLite database (`/app/data/watchlist.db`) will be reset on every deployment or instance restart. For persistent storage, migrate to Cloud SQL or Firestore.

### GitHub CI/CD Setup

#### Pull-Request CI Trigger (cloudbuild-ci.yaml)

Used for all pull requests. Runs tests and builds, never deploys:

- Installs backend dependencies
- Runs backend tests
- Installs frontend dependencies (using lockfile)
- Runs frontend tests
- Builds production frontend
- Validates Docker build (no push, no deploy)
- Fails immediately on any test or build failure

#### Main-Branch Deployment Trigger (cloudbuild.yaml)

Used only for main branch pushes. Performs full deployment:

1. Installs and runs backend tests
2. Installs and runs frontend tests
3. Builds production frontend
4. Builds Docker image
5. Tags image with `$SHORT_SHA`
6. Pushes image to Artifact Registry
7. Deploys exact image to Cloud Run

**Cloud Run deployment settings:**
- Service: `cinequeue`
- Region: `us-west1`
- Runtime service account: `cinequeue-runner@cinequeue-inouye-2026.iam.gserviceaccount.com`
- Minimum instances: 0
- Maximum instances: 1
- Allow unauthenticated access
- TMDB_API_KEY from Secret Manager secret `tmdb-api-key`
- Port: 8080

### Cloud Build Substitutions

Default substitutions in `cloudbuild.yaml`:
```yaml
_REGION: us-west1
_REPOSITORY: cinequeue
_SERVICE: cinequeue
_RUNTIME_SERVICE_ACCOUNT: cinequeue-runner@cinequeue-inouye-2026.iam.gserviceaccount.com
_TMDB_SECRET: tmdb-api-key
```

### Verifying Deployment

After deployment, verify the health endpoint:

```bash
curl https://cinequeue-<hash>-<region>.a.run.app/api/health
```

Expected response: `{"status": "ok", "tmdb_configured": true}`

## Features

- Personal watch queue (SQLite - temporary on Cloud Run)
- Upcoming movies, in-theatres, trending, and TV on-air
- Days until release / next episode
- Streaming, rent, buy, and theatre availability (US, via TMDB/JustWatch)
- Aggregated TMDB reviews
- Latest headlines from Google News RSS

## Future ML hooks

The Python backend is structured so you can add recommendation or sentiment models under `backend/app/services/` without changing the React UI.

## CI/CD Pipeline

- Pull requests into main run cloudbuild-ci.yaml.
- Merges into main run cloudbuild.yaml.
- Successful main builds deploy Cinequeue to Google Cloud Run.
