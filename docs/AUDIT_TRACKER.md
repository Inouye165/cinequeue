# CineQueue Comprehensive Audit & Remediation Tracker

This document tracks all **22 verified findings** across Security, Infrastructure, Race Conditions & Concurrency, Modularity, and Regression Test Coverage, fixed incrementally one item at a time.

**Branch:** `fix/comprehensive-app-audit`  
**Status:** `12 / 22` completed

---

## Checklist

### Test Harness Hygiene
- [x] **Item 1 (`[TEST-01]`)** — Fix Test Harness Module-Reload Isolation, Shadowed Duplicate Tests, & Live Network Calls in Unit Tests

### Security
- [x] **Item 2 (`[SEC-01]`)** — Authenticate `/api/sports`, Fix Cloud Run UTC Evening Game Drop & Fake Fallback Games, & Fix Empty Schedule Client Fallback
- [x] **Item 3 (`[SEC-02]`)** — Enforce Cookie CSRF & Origin Validation Across All Mutating Routers + Attach `X-CSRF-Token` in `syncService.ts`
- [x] **Item 4 (`[SEC-03]`)** — Production CORS/Origin Hardening, Fail-Closed Config Checks, & Root-Anchored `DATA_DIR`
- [x] **Item 5 (`[SEC-04]`)** — Bearer Token `email_verified` Enforcement, Approval Fail-Closed, Admin Dual-Auth Fallback, & `X-Session-Restore` Hardening
- [x] **Item 6 (`[SEC-05]`)** — Admin Auth Hardening: Timing-Safe Login, Brute-Force Rate Limiter, Hashed Session IDs, Startup Seeding Guard, & Proxy Cookie Stripping
- [x] **Item 7 (`[SEC-06]`)** — Fix `scrub_secrets` Telemetry Corruption & Eliminate `TMDB_API_KEY` / `GEMINI_API_KEY` / `auth_perf` Log Leaks
- [x] **Item 8 (`[SEC-07]`)** — Proxy Streaming/Traversal Hardening, CSP Clickjacking Headers, Verified SMTP TLS, Strict Input Schemas, & Frontend XSS/CSP Fixes
- [x] **Item 9 (`[SEC-08]`)** — Frontend Logout & Shared-Device Privacy Hygiene (`clearLocalData`, Scoped Caches, & Debug Log Cleanup)

### Infrastructure & Reliability
- [x] **Item 10 (`[INF-01]`)** — Replace Fragile `check_tmdb_key` Middleware with `movies.router` Dependency & Stop False-200 DB Error Swallowing
- [x] **Item 11 (`[INF-02]`)** — Bounded Caches, Deep-Copied Cache Reads, Cloud Run Log-Leak Fix, Query Bounds, & Enrichment Semaphore
- [x] **Item 12 (`[INF-03]`)** — Dockerfile `exec` PID-1 Signal Handling, Least-Privilege Permissions, `.dockerignore`/`.gitignore` Hardening & Dependency Split
- [ ] **Item 13 (`[INF-04]`)** — Cloud Build CI/CD Parity, Vite Preview Port 5180 Enforcement, Dev PWA Guard & Startup Script Cleanup

### Race Conditions & Concurrency
- [ ] **Item 14 (`[RACE-01]`)** — SQLite `WAL` + `busy_timeout`, Atomic `claim_daily_greeting_generation`, & `BriefingService` Step 4 Concurrent Wait Fix
- [ ] **Item 15 (`[RACE-02]`)** — Transactional Repository Mutations, Watchlist/Ratings Dual-Store Sync, Deterministic Hashing & Firestore Slash-Safe IDs
- [ ] **Item 16 (`[RACE-03]`)** — Offload Blocking Auth/DB Work Off Async Event Loop & Share Lifespan `httpx.AsyncClient`
- [ ] **Item 17 (`[RACE-04]`)** — Fix `SyncStatusBar` Zombie-Movie Bug, `syncLock` `ifAvailable` Semantics, & Protocol v2 Type Alignment
- [ ] **Item 18 (`[RACE-05]`)** — Fix `ActionConfirmationModal` Always-Empty Bug, Route `AgentModal` & `BatchRateModal` Through Local-First `movieService`, & Fix `AuthContext` 401 Stuck Banner
- [ ] **Item 19 (`[RACE-06]`)** — Add Request Cancellation (`AbortController`), Live Search Debouncing, & Optimistic/Offline Sports Preferences Sync

### Modularity & Regression Tests
- [ ] **Item 20 (`[MOD-01]`)** — Fix AI Agent Chat Persistence (`role="user"`), Firestore `DESCENDING` Chat Order, Pronoun Bug, Valid Statuses, Persona Presets & News Provider
- [ ] **Item 21 (`[MOD-02]`)** — Backend Modularity: Extract Shared Repository Helpers & Deduplicate Gemini Telemetry Logging
- [ ] **Item 22 (`[MOD-03]` & `[TEST-02]`)** — Frontend Modularity Cleanup & Comprehensive Security / Concurrency / Sports Regression Test Suite

---

## Detailed Findings & Fix Summaries

### 1. `[TEST-01]` Test Harness Isolation, Shadowed Tests & Live Network Calls (High)
- **Files**: `backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_auth.py`, `backend/tests/test_admin.py`, `backend/tests/test_news_and_weather_briefing.py`
- **Root Cause**: `client_with_auth` / `client_with_admin_auth` only reload a subset of router modules (skipping `sync`, `ratings`, `agent`, `sports`, `admin`) and `conftest.py` never restores defaults after `yield`; `test_api.py` has 5 shadowed duplicate test functions (lines 442–635 vs 637–832) including a stray `assert response.status_code == 404` and makes live `fetch_news` calls; `test_news_and_weather_briefing.py` makes live weather/Gemini network calls.
- **Fix Summary**: Introduce shared `reload_all_app_modules()` helper reloading all 8 routers; restore env on teardown; remove duplicate test block in `test_api.py`; mock `fetch_news` and external weather/network calls in unit tests.

### 2. `[SEC-01]` Unauthenticated `/api/sports`, UTC Evening Drop, Fake Fallback Games & Empty Schedule Client Fallback (High)
- **Files**: `backend/app/routers/sports.py`, `backend/app/services/sports_service.py`, `frontend/src/pages/CinequeueDashboard.tsx`, `frontend/src/services/sportsService.ts`
- **Root Cause**: `/api/sports/catalog` and `/api/sports/schedule?force_refresh=true` lack `get_current_user`; `get_sports_preferences` swallows DB errors returning `200` empty defaults; `sports_service.py` uses UTC on Cloud Run filtering out evening US games and substituting hardcoded fake games even when ESPN returned `200` with 0 games; `tracked_teams` parameter is ignored; frontend treats `{ games: [] }` as failure and falls back to stale cache.
- **Fix Summary**: Require `Depends(get_current_user)` on `sports.router`; raise `503` on DB error in `get_sports_preferences`; anchor schedule date window to `America/New_York`; track `upstream_succeeded` to return fake fallback games only on upstream failure; add 30s `force_refresh` cooldown; implement `tracked_teams` filtering; fix frontend empty array handling and skip unauthenticated `/api/sports/*` calls.

### 3. `[SEC-02]` Cookie CSRF & Origin Validation Missing Across Mutating Routers (High)
- **Files**: `backend/app/auth.py`, `backend/app/routers/auth.py`, `backend/app/routers/admin.py`, `backend/app/routers/watchlist.py`, `backend/app/routers/ratings.py`, `backend/app/routers/sync.py`, `backend/app/routers/sports.py`, `backend/app/routers/agent.py`, `frontend/src/api.ts`, `frontend/src/services/syncService.ts`
- **Root Cause**: State-changing user endpoints accept ambient session cookies without checking `Origin` or `X-CSRF-Token`; `admin.py` skips `validate_origin`; `validate_csrf` logs raw CSRF tokens; `syncService.ts` omits `X-CSRF-Token` header.
- **Fix Summary**: Centralize `validate_origin`, `validate_csrf` (with redacted logging), and `require_cookie_csrf_and_origin` dependency in `app/auth.py`; attach to all mutating user routers; enforce `validate_origin` in `admin.py`; attach `X-CSRF-Token` in `syncService.ts`.

### 4. `[SEC-03]` Production CORS/Origin Hardening, Unreachable Config Checks & `DATA_DIR` Drift (High)
- **Files**: `cloudrun-env.yaml`, `backend/app/config.py`
- **Root Cause**: `cloudrun-env.yaml` trusts plaintext `localhost` origins in production; `config.py` applies localhost defaults unconditionally even in `production`, making the production check unreachable dead code; `AUTH_MODE` and `SESSION_COOKIE_DAYS` are unvalidated; relative `DATA_DIR` depends on CWD causing split-brain SQLite files.
- **Fix Summary**: Remove localhost origins from `cloudrun-env.yaml` and add `APP_BASE_URL`; restrict localhost origin fallback in `config.py` to non-production; validate `AUTH_MODE` and `1 <= SESSION_COOKIE_DAYS <= 14`; anchor relative `DATA_DIR` to `ROOT_DIR`.

### 5. `[SEC-04]` Bearer `email_verified`, Approval Fail-Closed, Admin Cookie Fallback & `X-Session-Restore` Hardening (High)
- **Files**: `backend/app/auth.py`, `backend/app/services/admin_auth.py`, `backend/app/routers/auth.py`, `frontend/src/api.ts`, `frontend/src/context/AuthContext.tsx`
- **Root Cause**: Bearer token paths in `get_current_user` and `get_current_admin` omit `email_verified` checks; `get_current_user` fails open when `AUTH_MODE != "allowlist"`; standard-user Bearer token blocks fallback to valid `cinequeue_admin_session` cookie; `X-Session-Restore: 1` relaxes `auth_time` to 1 year without checking revocation; `/api/auth/logout` does not revoke Firebase refresh tokens.
- **Fix Summary**: Enforce `email_verified` on Bearer paths; fail closed for unapproved users regardless of `AUTH_MODE`; allow admin cookie fallback when Bearer user isn't admin; cap `X-Session-Restore` `auth_time` at 30 days with `check_revoked=True` and only send `X-Session-Restore: 1` when restoring; revoke refresh tokens on logout.

### 6. `[SEC-05]` Admin Auth Hardening (High)
- **Files**: `backend/app/main.py`, `backend/app/services/admin_auth.py`, `backend/app/routers/admin.py`, `backend/manage_admins.py`
- **Root Cause**: Startup seeds default admin even when `ENABLE_FALLBACK_ADMIN_AUTH=false` and accepts `.env.example` placeholder password; `firebase_auth_proxy` forwards `cinequeue_admin_session`; username timing oracle & synchronous PBKDF2 on event loop; no rate limiting; raw session tokens stored in DB with mixed-case username mismatch; `manage_admins.py` lacks password length check and session cleanup.
- **Fix Summary**: Gate startup admin seeding behind `ENABLE_FALLBACK_ADMIN_AUTH` and non-placeholder password; strip admin session cookies in proxy; store SHA-256 hashed session tokens; normalize usernames; run dummy PBKDF2 in `asyncio.to_thread` on missing user; add IP sliding-window brute-force rate limiter; enforce >=12-char passwords and clear sessions in `manage_admins.py`.

### 7. `[SEC-06]` `scrub_secrets` Telemetry Corruption & `TMDB_API_KEY` / `GEMINI_API_KEY` / `auth_perf` Log Leaks (High)
- **Files**: `backend/app/decision_models.py`, `backend/app/services/agent_service.py`, `backend/app/services/tmdb.py`, `backend/app/routers/movies.py`, `backend/app/auth_perf.py`
- **Root Cause**: Substring matching on `"key"` and `"token"` overwrites `daily_cache_key`, `item_key`, and all `*_token_count` metrics with `"[REDACTED]"`, while `SECRET_PATTERNS` is dead code; `httpx.HTTPStatusError` embeds `?api_key=<TMDB_API_KEY>` in logs and 500 responses; `GEMINI_API_KEY` is in query string; `auth_perf` logs raw malformed `Authorization` headers and unvalidated `X-Auth-Trace-Id`.
- **Fix Summary**: Use exact secret key matching and apply `SECRET_PATTERNS` in `scrub_secrets`/`sanitize_log_data`; scrub `api_key` in `TmdbClient._get` and translate upstream HTTP errors to `404`/`502` in `movies.py`; send `GEMINI_API_KEY` in `x-goog-api-key` header; allowlist `authorization_header_scheme` and validate `X-Auth-Trace-Id`.

### 8. `[SEC-07]` Proxy Hardening, Clickjacking CSP, Verified SMTP TLS, Input Validation & Frontend XSS/CSP (High)
- **Files**: `backend/app/main.py`, `backend/app/services/email_service.py`, `backend/app/routers/admin.py`, `backend/app/routers/ratings.py`, `backend/app/routers/sync.py`, `backend/app/services/weather_provider.py`, `frontend/src/components/DetailModal.tsx`, `frontend/index.html`
- **Root Cause**: CSP omits `frame-ancestors` and `X-Frame-Options`; `firebase_auth_proxy` buffers unbounded chunked bodies, allows `..`/arbitrary paths, and trusts `Host` header; `email_service.py` calls `starttls()` without SSL context and leaks exceptions; unvalidated `email`/`media_type` allow Firestore `/` path injection; `weather_provider.py` allows `/` in `quote()`; `DetailModal.tsx` renders unvalidated `href`/`trailer.key`/`backdrop_url`; `index.html` has CSP-violating inline `onload` on Google Fonts.
- **Fix Summary**: Add `frame-ancestors 'none'` and `X-Frame-Options: DENY`; stream-cap proxy body at 64 KB, allowlist helper paths, and validate fallback host; verify SMTP TLS via `ssl.create_default_context()`; validate emails, `Literal["movie", "tv"]`, and `safe=""` quoting; sanitize URLs with `toSafeHttpUrl` and remove inline `onload` in `index.html`.

### 9. `[SEC-08]` Frontend Logout & Shared-Device Privacy Hygiene (High)
- **Files**: `frontend/src/services/movieService.ts`, `frontend/src/services/sportsService.ts`, `frontend/src/components/AgentLoginBriefing.tsx`, `frontend/src/pages/CinequeueDashboard.tsx`, `frontend/src/context/AuthContext.tsx`, `frontend/src/utils/authDebugLog.ts`, `frontend/src/utils/authPerformanceMonitor.ts`, `frontend/src/components/AuthDiagnosticsPanel.tsx`
- **Root Cause**: `clearLocalData(ownerId)` leaves `recovery:*`, `healed_sync:*`, and `sports_prefs:*`; `sports_schedule` and `cinequeue_briefing_session_id` are not owner-scoped; `logout()` fails to clear `authDebugLog` and `traceHistory`; `?debug` exposes diagnostics panel (with prior user PII) in production; debug log sanitizers are non-recursive.
- **Fix Summary**: Clean all owner-scoped metadata keys on `clearLocalData`; scope `sports_schedule` and briefing session keys by `ownerId`; recursively redact secrets/JWTs; clear debug logs and trace history on `logout()`; gate `AuthDiagnosticsPanel` behind `DEV || isAdmin`.

### 10. `[INF-01]` Replace `check_tmdb_key` Middleware & Stop False-200 DB Error Swallowing (High)
- **Files**: `backend/app/main.py`, `backend/app/routers/movies.py`, `backend/app/routers/ratings.py`, `backend/app/firestore_repo.py`
- **Root Cause**: `check_tmdb_key` middleware blocks `/api/admin/*` when `TMDB_API_KEY` is missing and strips CORS/security headers from 503 responses; `ratings.py` and `firestore_repo.list_rated_movies` return `200 []` or `200 {"success": True}` on DB errors.
- **Fix Summary**: Replace `check_tmdb_key` middleware with `require_tmdb_client` dependency on `movies.router`; propagate DB errors as `500`/`503` HTTP responses instead of fake `200` empty/success payloads.

### 11. `[INF-02]` Bounded Caches, Deep-Copied Cache Reads, Log-Leak Fix, Query Bounds & Enrichment Semaphore (High)
- **Files**: `backend/app/logging_config.py`, `backend/app/services/tmdb.py`, `backend/app/services/weather_service.py`, `backend/app/services/sports_service.py`, `backend/app/routers/watchlist.py`, `backend/app/routers/admin.py`, `backend/app/routers/agent.py`, `backend/app/routers/sync.py`, `backend/app/firestore_repo.py`
- **Root Cause**: Production `FileHandler` leaks Cloud Run `tmpfs` RAM and risks `cp1252` crashes; `TmdbClient._cache` is unbounded and returns mutable dict references mutated by `watchlist.py`; `weather_service` and `sports_service` caches are unbounded; `watchlist.py` fires unbounded concurrent TMDB calls; log endpoints lack `limit`/`offset` bounds and stream entire Firestore collections; `sync` batch and `agent` inputs are unbounded.
- **Fix Summary**: Disable file logging in production and use UTF-8 `RotatingFileHandler` in dev; bound caches (`OrderedDict` LRU) and `deepcopy` cached `TmdbClient` values; cache `fetch_news` and reuse `get_details` in `get_release_info`; bound enrichment with `asyncio.Semaphore(8)`; bound query/payload sizes and Firestore `.limit()`.

### 12. `[INF-03]` Dockerfile Hardening, `.dockerignore`/`.gitignore` & Dependency Split (Medium)
- **Files**: `Dockerfile`, `.dockerignore`, `.gitignore`, `backend/requirements.txt`, `backend/requirements-dev.txt`
- **Root Cause**: `CMD` uses `sh` without `exec` preventing graceful `SIGTERM`; entire `/app` writable by `appuser`; no `HEALTHCHECK`; `.dockerignore` misses `*.key`, `*.pem`, `service-account*.json`, `tests/`, `data/`, `cloudrun-env.yaml`; test tools installed in production image and direct deps (`pydantic`, `requests`) unpinned.
- **Fix Summary**: Use `exec uvicorn`, restrict `appuser` ownership to `/app/data`, add `HEALTHCHECK`; harden `.dockerignore` and `.gitignore`; move `pytest`/`pytest-asyncio` to `requirements-dev.txt` and pin runtime deps.

### 13. `[INF-04]` Cloud Build CI/CD Parity, Vite Preview Port 5180, Dev PWA Guard & Scripts (Medium)
- **Files**: `cloudbuild.yaml`, `cloudbuild-ci.yaml`, `frontend/vite.config.ts`, `frontend/playwright.config.ts`, `.env.example`, `dev.ps1`, `start.ps1`, `push_pr.ps1`
- **Root Cause**: `cloudbuild-ci.yaml` omits `PYTHONPATH=backend`; both pipelines rebuild frontend 3 times; `vite.config.ts` lacks `preview` port `5180` config, uses `as any`, enables SW in dev mode, and duplicates maskable icons; `dev.ps1` matches generic `"vite"` keyword; `start.ps1` duplicates `dev.ps1`; `push_pr.ps1` hardcodes an old branch and pushes automatically.
- **Fix Summary**: Fix CI/CD parity and `PLAYWRIGHT_SKIP_REBUILD=1`; configure `preview` on port `5180`, import from `vitest/config`, gate `devOptions.enabled`, clean manifest icons; fix `.env.example`, `dev.ps1`, `start.ps1`, and `push_pr.ps1`.

### 14. `[RACE-01]` SQLite WAL, Atomic Briefing Claim & Concurrent Generation Wait (Critical)
- **Files**: `backend/app/sqlite_repo.py`, `backend/app/firestore_repo.py`, `backend/app/services/briefing_service.py`
- **Root Cause**: SQLite omits WAL mode and `BEGIN IMMEDIATE` in `claim_daily_greeting_generation`; Firestore fails open with `(True, None)` on exception; `BriefingService` Step 4 does not wait when losing the generation race and persists a bogus fallback message into chat history; `ContextVar` token is not reset in `finally`.
- **Fix Summary**: Enable `WAL` + `busy_timeout`; use `BEGIN IMMEDIATE` in SQLite `claim_daily_greeting_generation`; fail closed `(False, None)` in Firestore; share poll-wait helper in Step 4 and avoid persisting bogus fallback on in-flight race; reset `ContextVar` in `finally`.

### 15. `[RACE-02]` Transactional Repo Mutations, Dual-Store Sync, Deterministic Hashing & Slash-Safe IDs (High)
- **Files**: `backend/app/firestore_repo.py`, `backend/app/sqlite_repo.py`, `backend/app/routers/watchlist.py`, `backend/app/routers/sync.py`, `backend/app/services/briefing_service.py`
- **Root Cause**: Non-atomic read-modify-write in `add_item`, `update_item`, `save_sports_preferences`, `save_decision_config`, `save_prompt_version`, `record_briefing_presentations`; `watchlist` and Protocol v1 `sync` endpoints desync `watchlist` and `rated_movies` (including deleting upserted `watched` items when `rating=0`); randomized Python `hash()` used for DB IDs; unhashed `/` in titles crashes Firestore doc paths; thread-unsafe `_restoration_cache`.
- **Fix Summary**: Use atomic `create()` / transactions / `BEGIN IMMEDIATE`; synchronize dual-store mutations and fix Protocol v1 delete/upsert; replace `hash()` with SHA-256; SHA-256 hash Firestore doc IDs in `add_query_memory` and `record_briefing_presentations`; lock `_restoration_cache`.

### 16. `[RACE-03]` Offload Blocking Auth/DB I/O Off Event Loop & Share `httpx.AsyncClient` (High)
- **Files**: `backend/app/main.py`, `backend/app/auth.py`, `backend/app/routers/auth.py`, `backend/app/services/admin_auth.py`, `backend/app/routers/ratings.py`, `backend/app/routers/sync.py`, `backend/app/routers/sports.py`, `backend/app/routers/agent.py`
- **Root Cause**: Synchronous Firebase/PBKDF2/Firestore/SQLite calls run directly on Uvicorn's single async event loop; `firebase_auth_proxy` creates a fresh `httpx.AsyncClient` per request.
- **Fix Summary**: Share lifespan-managed `app.state.http_client`; offload Firebase/PBKDF2/repo calls in auth paths via `asyncio.to_thread`; convert synchronous DB-only endpoints to `def`.

### 17. `[RACE-04]` `SyncStatusBar` Zombie-Movie Bug, `syncLock` `ifAvailable` & Protocol v2 Alignment (Critical)
- **Files**: `frontend/src/components/SyncStatusBar.tsx`, `frontend/src/services/syncLock.ts`, `frontend/src/services/syncService.ts`, `frontend/src/components/DeviceDataPanel.tsx`, `frontend/src/db/cinequeueDb.ts`, `frontend/src/services/movieService.ts`
- **Root Cause**: `SyncStatusBar` mutates payloads under existing `operationId`s or deletes failed ops without resetting `db.movies.syncStatus` (stranding permanent `pending_push` zombies); `clearWorkspace` queues behind `navigator.locks` then wipes newly synced data; IndexedDB lock heartbeat can abort after release; TypeScript types allow `"archived"`/`"patch"` rejected with `422` by backend.
- **Fix Summary**: Remove destructive auto-healer; acquire `withSyncLock(..., { ifAvailable: true })` on dismiss/clear/restore and reset `syncStatus` on dismiss; guard heartbeat against released state; align `LocalMovie["status"]` and `SyncOperation["operationType"]` with backend Protocol v2.

### 18. `[RACE-05]` `ActionConfirmationModal` Always-Empty, Modal Sync Bypass & `AuthContext` 401 Stuck Banner (Critical/High)
- **Files**: `frontend/src/components/ActionConfirmationModal.tsx`, `frontend/src/components/AgentModal.tsx`, `frontend/src/components/BatchRateModal.tsx`, `frontend/src/pages/CinequeueDashboard.tsx`, `frontend/src/context/AuthContext.tsx`
- **Root Cause**: `ActionConfirmationModal` caches `proposedItems` in initial `useState([])` while permanently mounted; `AgentModal` and `BatchRateModal` mutate backend directly bypassing `movieService`/`db.syncQueue` and can pass `tmdb_id: 0`; `cinequeue-unauthorized` leaves `firebaseUser` and `authTokenStore` set, hiding `"Sign in to sync"` forever.
- **Fix Summary**: Sync `proposedItems` on open and conditionally mount modal; disallow `tmdb_id: 0`; route modal mutations through `movieService` + `syncService`; guard `"⭐ Add Ratings"` when `!user`; clear token and `firebaseUser` on `401` and update `authTokenStore` on `refreshAdminState`.

### 19. `[RACE-06]` `AbortController` Cancellation, Live Search Debounce & Sports Preferences Sync (Medium-High)
- **Files**: `frontend/src/api.ts`, `frontend/src/pages/CinequeueDashboard.tsx`, `frontend/src/components/BatchRateModal.tsx`, `frontend/src/components/admin/AiAgentDecisionsTab.tsx`, `frontend/src/components/AgentLoginBriefing.tsx`, `frontend/src/services/sportsService.ts`
- **Root Cause**: Search tab and admin log filters fire un-debounced, un-aborted requests on every keystroke; `BatchRateModal`, `openDetails`, and `AgentLoginBriefing` ignore request cancellation; rapid streaming service toggles drop updates due to stale closures; `syncPreferencesFromServer` discards newer local edits when remote `setup_completed` is true.
- **Fix Summary**: Add `AbortSignal` across `api.*`, debounce live search/filter inputs, abort on cleanup/close; use functional/serialized state updates for sports prefs; push newer local sports prefs when `local.updated_at > remote.updated_at`.

### 20. `[MOD-01]` AI Agent Chat Persistence, Firestore Order, Pronoun Bug, Statuses & News Provider (Critical/High)
- **Files**: `backend/app/services/agent_service.py`, `backend/app/firestore_repo.py`, `backend/app/routers/agent.py`, `backend/app/routers/watchlist.py`, `backend/app/services/news_service.py`
- **Root Cause**: `process_chat` never persists `role="user"` messages; Firestore `list_chat_messages` queries `ASCENDING` returning oldest messages forever; `"it" in msg_lower` triggers accidental watchlist adds; `"watching"`/`"dropped"` corrupt watchlist statuses; `PERSONALITY_PRESETS`, `rating_rec_note`, and `auto_speak_briefing` are disconnected; duplicate `_get_time_of_day` uses UTC; `TmdbEntertainmentNewsProvider` calls nonexistent `tmdb.get_news()`.
- **Fix Summary**: Persist `role="user"` messages; query Firestore chat `DESCENDING` then reverse; fix word-boundary pronoun + explicit verb check; honor `auto_add_mentioned`; allow `"watched"` and map agent statuses cleanly; wire `PERSONALITY_PRESETS`, `rating_rec_note`, `auto_speak_briefing`, and timezone-aware `_get_time_of_day`; fix `TmdbEntertainmentNewsProvider`.

### 21. `[MOD-02]` Backend Modularity: Extract Shared Repo Helpers & Deduplicate Telemetry Logging (Medium)
- **Files**: `backend/app/repo_helpers.py` (new), `backend/app/sqlite_repo.py`, `backend/app/firestore_repo.py`, `backend/app/decision_models.py`, `backend/app/services/agent_service.py`, `backend/app/services/briefing_service.py`, `backend/app/services/decision_engine.py`, `backend/app/routers/admin.py`
- **Root Cause**: Identical formatting, deduplication, default dicts, and telemetry normalization duplicated across `sqlite_repo.py` and `firestore_repo.py`; `DecisionConfig(**dict)`/`PromptVersion(**dict)` crash on unknown keys; `_call_gemini_api` repeats an 8x copy-pasted 30-key telemetry dictionary.
- **Fix Summary**: Extract `backend/app/repo_helpers.py`; add `from_dict()` on `DecisionConfig` and `PromptVersion`; extract `_log_gemini_event` helper in `agent_service.py`.

### 22. `[MOD-03]` & `[TEST-02]` Frontend Modularity Cleanup & Comprehensive Regression Test Suite (Medium/High)
- **Files**: `frontend/src/pages/CinequeueDashboard.tsx`, `frontend/src/components/AgentModal.tsx`, `frontend/src/components/AccountSheet.tsx`, `frontend/src/types.ts`, `frontend/src/utils/releaseUtils.ts`, `backend/tests/test_sports.py`, `backend/tests/test_security_and_concurrency_regressions.py`, `frontend/src/**/*.test.tsx`
- **Root Cause**: Duplicated rating/speech/badge logic, broken interface overrides (`WatchlistItem`, `MediaDetails`), dead `releaseUtils.ts`, and major test blind spots (zero sports tests, missing CSRF/proxy/XSS/concurrency/sync/logout hygiene tests).
- **Fix Summary**: Deduplicate frontend helpers, fix `types.ts`, delete dead `releaseUtils.ts`; add comprehensive backend and frontend regression suites covering all fixed vulnerabilities and race conditions.
