import os
import uuid
import time
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Control detailed log outputs via environment flag
AUTH_PERFORMANCE_DEBUG = os.getenv("AUTH_PERFORMANCE_DEBUG", "false").strip().lower() == "true"

def log_trace(perf_data: dict, status_code: int, total_duration_ms: float, result: str):
    """Outputs structured JSON performance details to stdout/logs."""
    if not AUTH_PERFORMANCE_DEBUG:
        return

    log_data = {
        "traceId": perf_data.get("trace_id"),
        "requestId": perf_data.get("request_id"),
        "route": perf_data.get("route"),
        "statusCode": status_code,
        "totalDurationMs": total_duration_ms,
        "tokenVerificationDurationMs": perf_data.get("token_verification_duration_ms", 0.0),
        "adminLookupDurationMs": perf_data.get("admin_lookup_duration_ms", 0.0),
        "authorizationHeaderPresent": perf_data.get("authorization_header_present", False),
        "authorizationHeaderScheme": perf_data.get("authorization_header_scheme", "None"),
        "result": result
    }

    logger.info("[AuthPerformance] %s", json.dumps(log_data))

class AuthPerfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_admin_me = path == "/api/admin/me"

        # Generate request ID
        req_id = str(uuid.uuid4())
        request.state.request_id = req_id

        # Extract X-Auth-Trace-Id
        trace_id = request.headers.get("X-Auth-Trace-Id")
        request.state.trace_id = trace_id

        # Start timing
        start_time = time.perf_counter()
        
        # Initialize trace structure in request state
        request.state.auth_perf = {
            "trace_id": trace_id,
            "request_id": req_id,
            "route": path,
            "start_time": start_time,
            "timings": {
                "request_received": start_time,
            },
            "token_verification_duration_ms": 0.0,
            "admin_lookup_duration_ms": 0.0,
            "authorization_header_present": False,
            "authorization_header_scheme": "None",
        }

        # Check authorization header presence / scheme
        auth_header = request.headers.get("Authorization")
        if auth_header:
            request.state.auth_perf["authorization_header_present"] = True
            parts = auth_header.split()
            request.state.auth_perf["authorization_header_scheme"] = parts[0] if parts else "Unknown"
        
        request.state.auth_perf["timings"]["authorization_header_checked"] = time.perf_counter()

        # Firebase token verification placeholders (for /api/admin/me, these are skipped)
        request.state.auth_perf["timings"]["firebase_token_verification_started"] = time.perf_counter()
        request.state.auth_perf["timings"]["firebase_token_verification_completed"] = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as e:
            if is_admin_me:
                total_dur = (time.perf_counter() - start_time) * 1000.0
                log_trace(request.state.auth_perf, 500, total_dur, "error")
            raise e

        # Append headers to the response
        if trace_id:
            response.headers["X-Auth-Trace-Id"] = trace_id
            
        if is_admin_me:
            tv_ms = request.state.auth_perf.get("token_verification_duration_ms", 0.0)
            al_ms = request.state.auth_perf.get("admin_lookup_duration_ms", 0.0)
            response.headers["X-Auth-Perf-Token-Verification-Ms"] = f"{tv_ms:.3f}"
            response.headers["X-Auth-Perf-Admin-Lookup-Ms"] = f"{al_ms:.3f}"

            # Log trace details
            total_dur = (time.perf_counter() - start_time) * 1000.0
            log_trace(request.state.auth_perf, response.status_code, total_dur, "success" if response.status_code < 400 else "failure")

        return response
