# Authentication Performance Monitoring Documentation

This temporary performance-monitoring system instruments and traces the complete authentication flow across both the frontend and backend of CineQueue.

---

## 1. How to Enable Tracing

### Frontend (Diagnostics Panel & Console Summary)
Set the environment flag in your frontend `.env` file (or build environment):
```ini
VITE_AUTH_PERFORMANCE_DEBUG=true
```
*When enabled, this displays a floating dashboard overlay at the bottom-right of the screen and outputs structured console tables on flow completion.*

### Backend (Detailed Structured Timing Logs)
Set the environment flag in your backend `.env` file:
```ini
AUTH_PERFORMANCE_DEBUG=true
```
*When enabled, this prints structured JSON metrics to the console for every `/api/admin/me` request.*

---

## 2. How to Reproduce a Login & Read Traces

1. Start both development servers (frontend and backend).
2. Open the browser and navigate to `http://localhost:5180`.
3. Locate the floating badge **⏱️ Auth Diagnostics** in the bottom-right corner.
4. Click on it to expand the tracing dashboard overlay.
5. Trigger a login cycle by logging in as an administrator or using Google Sign-In.
6. The dashboard will automatically update with:
   - **Chronological Logs:** Step-by-step lifecycle checkpoints with exact execution and elapsed times.
   - **Duration Summary:** Aggregated timing measurements (e.g. Firebase config fetching, initialization, session restoration, backend admin lookup).
   - **Diagnostics Counts:** Tracking duplicates, StrictMode mounts, and cleanups.
   - **Warnings:** Flags for slow operations (>500ms or >1000ms), premature requests, or duplicate uvicorn calls.

---

## 3. How to Export Traces

In the expanded diagnostics overlay, click **Copy Sanitized Trace** to copy a clean JSON representation of the latest trace to your clipboard. This can be shared with developers to locate performance bottlenecks.

---

## 4. What Information is Intentionally Never Logged

To comply with security and privacy requirements, the tracing system **completely sanitizes and never logs or exports**:
* Firebase ID tokens
* API keys
* User passwords
* Authorization headers
* Browser session cookies
* Full user database records

It only captures safe operational telemetry such as:
* Timings (using `performance.now()`)
* Execution status (`start`, `success`, `failure`, `skipped`)
* Trace ID and Request ID UUIDs
* Token presence & length
* UI state loading status
* HTTP status codes

---

## 5. How to Disable & Remove the Monitoring

### Disabling
Simply set the variables in `.env` to `false`:
```ini
VITE_AUTH_PERFORMANCE_DEBUG=false
AUTH_PERFORMANCE_DEBUG=false
```

### Complete Removal
To completely remove this temporary instrument:
1. Delete [authPerformanceMonitor.ts](file:///c:/Users/inouy/projects/cinequeue/frontend/src/utils/authPerformanceMonitor.ts), [AuthDiagnosticsPanel.tsx](file:///c:/Users/inouy/projects/cinequeue/frontend/src/components/AuthDiagnosticsPanel.tsx), and [authPerformanceMonitor.test.ts](file:///c:/Users/inouy/projects/cinequeue/frontend/src/utils/authPerformanceMonitor.test.ts).
2. Revert the imports and instrumentation checkpoints inside [AuthContext.tsx](file:///c:/Users/inouy/projects/cinequeue/frontend/src/context/AuthContext.tsx) and [api.ts](file:///c:/Users/inouy/projects/cinequeue/frontend/src/api.ts).
3. Revert `<AuthDiagnosticsPanel />` from [App.tsx](file:///c:/Users/inouy/projects/cinequeue/frontend/src/App.tsx).
4. Revert `AuthPerfMiddleware` from [main.py](file:///c:/Users/inouy/projects/cinequeue/backend/app/main.py) and remove the [auth_perf.py](file:///c:/Users/inouy/projects/cinequeue/backend/app/auth_perf.py) and [test_auth_perf.py](file:///c:/Users/inouy/projects/cinequeue/backend/tests/test_auth_perf.py) files.
5. Revert timing additions from [services/admin_auth.py](file:///c:/Users/inouy/projects/cinequeue/backend/app/services/admin_auth.py).
