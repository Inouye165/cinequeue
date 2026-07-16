# Cinequeue Configuration Guide

This document outlines all configuration options for Cinequeue and future home information services.

## Environment Variables

All sensitive configuration is stored in `.env` file (gitignored). Copy `.env.example` to `.env` and fill in values.

### Current Configuration

```bash
# TMDB API Configuration
TMDB_API_KEY=your_tmdb_api_key_here

# Data Storage
DATA_DIR=./data

# Backend Configuration
BACKEND_PORT=8001
BACKEND_HOST=127.0.0.1

# Frontend Configuration
FRONTEND_PORT=5180
```

### Future Services (Placeholders)

```bash
# Google Services
GOOGLE_API_KEY=
GOOGLE_CLOUD_PROJECT=

# AI/ML Services
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Database Services
DATABASE_URL=
REDIS_URL=

# External APIs
NEWS_API_KEY=
WEATHER_API_KEY=
```

## Security Guidelines

1. **Never commit `.env`** - It's in `.gitignore`
2. **Use `.env.example`** - Template with placeholder values only
3. **Rotate keys** - If a key is accidentally exposed, regenerate it
4. **Use `.env.local`** - For local overrides not shared with team
5. **Document new keys** - Add to `.env.example` when adding new services

## Adding New Services

When adding a new service to the home information repo:

1. Add the API key to `.env.example` as a placeholder
2. Add the key to your local `.env`
3. Update `backend/app/config.py` to load the new variable
4. Add logging for the new service initialization
5. Add tests for the new service configuration

## Current Secrets

- **TMDB_API_KEY**: Used for movie/TV data from The Movie Database
- **SQLite Database**: Stored in `backend/data/watchlist.db` (gitignored)

## File Structure

```
cinequeue/
├── .env                    # Actual secrets (gitignored)
├── .env.example            # Template (version controlled)
├── .gitignore              # Excludes sensitive files
├── backend/
│   ├── app/
│   │   └── config.py       # Loads environment variables
│   ├── data/               # Database files (gitignored)
│   └── logs/               # Application logs (gitignored)
└── frontend/
    └── vite.config.ts      # API proxy configuration
```

## Deployment

For Google Cloud Run deployment, set environment variables via:

```bash
gcloud run deploy cinequeue \
  --set-env-vars TMDB_API_KEY=your_key_here \
  --set-env-vars BACKEND_PORT=8000
```

## Troubleshooting

If API keys aren't loading:
1. Check `.env` exists in project root
2. Verify `backend/app/config.py` path resolution
3. Check backend logs for loading errors
4. Run health check: `curl http://localhost:8001/api/health`
