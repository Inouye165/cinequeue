# Cinequeue

Personal movie and TV tracker with release countdowns, where-to-watch info, reviews, and news.

## Stack

- **Frontend:** React + TypeScript (Vite)
- **Backend:** Python FastAPI
- **Data:** TMDB API + Google News RSS
- **Deploy:** Google Cloud Run (Docker) via GitHub CI/CD

## Local Development

### 1. Get a TMDB API key

Create a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).

### 2. Configure environment

```bash
cp .env.example .env
```

Set `TMDB_API_KEY` in `.env`.

### 3. Backend development

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend development (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The Vite dev server proxies `/api` to port 8000.

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
