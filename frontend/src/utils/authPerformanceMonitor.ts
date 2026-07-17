export interface AuthTraceEvent {
  traceId: string;
  event: string;
  timestamp: string; // ISO timestamp
  elapsedMs: number; // Time since start of trace
  durationMs?: number; // Duration of the operation
  status?: "start" | "success" | "failure" | "skipped";
  details?: Record<string, any>;
}

export interface TraceCounts {
  configFetches: number;
  initAttempts: number;
  listenersRegistered: number;
  callbacks: number;
  getIdTokenCalls: number;
  adminMeRequests: number;
  popupLogins: number;
  mounts: number;
  cleanups: number;
}

export interface AuthTrace {
  traceId: string;
  startTime: number; // performance.now()
  startTimeEpoch: number; // Date.now()
  events: AuthTraceEvent[];
  counts: TraceCounts;
  warnings: string[];
  backendTimings?: {
    tokenVerificationMs?: number;
    adminLookupMs?: number;
    totalBackendMs?: number;
  };
}

let traceHistory: AuthTrace[] = [];
let activeTrace: AuthTrace | null = null;
const MAX_HISTORY = 10;

// Mapping of completion events to their respective start events
const START_EVENT_MAP: Record<string, string> = {
  firebase_config_fetch_completed: "firebase_config_fetch_started",
  firebase_initialization_completed: "firebase_initialization_started",
  popup_login_completed: "popup_login_started",
  popup_login_failed: "popup_login_started",
  id_token_request_completed: "id_token_request_started",
  admin_me_response_received: "admin_me_request_started",
  admin_me_request_completed: "admin_me_request_started",
  admin_me_request_failed: "admin_me_request_started",
  auth_context_state_update_completed: "auth_context_state_update_started",
  auth_state_callback_completed: "auth_state_callback_started",
  csrf_request_completed: "csrf_request_started",
  session_creation_completed: "session_creation_started",
  profile_request_completed: "profile_request_started",
  profile_request_failed: "profile_request_started",
  admin_requests_completed: "admin_requests_started",
  admin_requests_skipped: "admin_requests_started",
};

/**
 * Generate a unique trace ID in the format auth-1721151234567-a8f3
 */
export function generateTraceId(): string {
  const timestamp = Date.now();
  const randomChars = Math.random().toString(36).substring(2, 6);
  return `auth-${timestamp}-${randomChars}`;
}

/**
 * Sanitizes sensitive fields from details object (tokens, keys, passwords, cookies, authorization headers)
 */
export function sanitizeDetails(details?: Record<string, any>): Record<string, any> | undefined {
  if (!details) return undefined;
  const sanitized: Record<string, any> = {};
  for (const [key, value] of Object.entries(details)) {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey.includes("token") ||
      lowerKey.includes("key") ||
      lowerKey.includes("password") ||
      lowerKey.includes("auth") ||
      lowerKey.includes("cookie") ||
      lowerKey.includes("credential") ||
      lowerKey.includes("secret")
    ) {
      if (typeof value === "string") {
        sanitized[key] = `[REDACTED (length: ${value.length})]`;
      } else {
        sanitized[key] = `[REDACTED]`;
      }
    } else {
      sanitized[key] = value;
    }
  }
  return sanitized;
}

/**
 * Start a new performance trace
 */
export function startTrace(): AuthTrace {
  const traceId = generateTraceId();
  const newTrace: AuthTrace = {
    traceId,
    startTime: performance.now(),
    startTimeEpoch: Date.now(),
    events: [],
    counts: {
      configFetches: 0,
      initAttempts: 0,
      listenersRegistered: 0,
      callbacks: 0,
      getIdTokenCalls: 0,
      adminMeRequests: 0,
      popupLogins: 0,
      mounts: 0,
      cleanups: 0,
    },
    warnings: [],
  };

  activeTrace = newTrace;
  traceHistory.push(newTrace);
  if (traceHistory.length > MAX_HISTORY) {
    traceHistory = traceHistory.slice(-MAX_HISTORY);
  }

  recordEvent("auth_trace_started", "start");
  return newTrace;
}

/**
 * Get the current active trace
 */
export function getActiveTrace(): AuthTrace | null {
  return activeTrace;
}

/**
 * Get the trace history (up to 10 traces)
 */
export function getTraceHistory(): AuthTrace[] {
  return traceHistory;
}

/**
 * Records an event in the active trace
 */
export function recordEvent(
  event: string,
  status?: "start" | "success" | "failure" | "skipped",
  details?: Record<string, any>
): AuthTraceEvent | null {
  if (!activeTrace) return null;

  const now = performance.now();
  const elapsedMs = now - activeTrace.startTime;
  let durationMs: number | undefined;

  // Compute duration if this is a completion event
  const matchingStartEvent = START_EVENT_MAP[event];
  if (matchingStartEvent) {
    // Find the last occurrence of the matching start event in this trace
    const startEventObj = [...activeTrace.events]
      .reverse()
      .find((e) => e.event === matchingStartEvent);

    if (startEventObj) {
      durationMs = elapsedMs - startEventObj.elapsedMs;
    }
  }

  const sanitizedDetails = sanitizeDetails(details);

  const traceEvent: AuthTraceEvent = {
    traceId: activeTrace.traceId,
    event,
    timestamp: new Date().toISOString(),
    elapsedMs,
    durationMs,
    status,
    details: sanitizedDetails,
  };

  activeTrace.events.push(traceEvent);

  // Register performance marks/measures in browser
  try {
    const markName = `cinequeue-auth:${activeTrace.traceId}:${event}`;
    performance.mark(markName);

    if (matchingStartEvent) {
      const startMarkName = `cinequeue-auth:${activeTrace.traceId}:${matchingStartEvent}`;
      const measureName = `cinequeue-auth:${activeTrace.traceId}:${event}_duration`;
      performance.measure(measureName, startMarkName, markName);
    }
  } catch (err) {
    // Catch browser performance API failures silently
  }

  if (event === "auth_trace_completed") {
    printConsoleSummary();
  }

  return traceEvent;
}

/**
 * Increment count for a tracked operation
 */
export function incrementCount(key: keyof TraceCounts) {
  if (activeTrace) {
    activeTrace.counts[key]++;
  }
}

/**
 * Record a warning on the active trace
 */
export function addWarning(warning: string) {
  if (activeTrace) {
    activeTrace.warnings.push(warning);
    console.warn(`[AuthPerformance] ${warning}`);
  }
}

/**
 * Detect duplicate calls to /api/admin/me
 */
export function detectDuplicateMeRequest() {
  if (!activeTrace) return;
  
  incrementCount("adminMeRequests");
  
  // Find previous admin_me_request_started event
  const previousRequests = activeTrace.events.filter(
    (e) => e.event === "admin_me_request_started"
  );

  if (previousRequests.length > 1) {
    const lastRequest = previousRequests[previousRequests.length - 2];
    const currentRequest = previousRequests[previousRequests.length - 1];
    const timeDiff = currentRequest.elapsedMs - lastRequest.elapsedMs;
    
    if (timeDiff < 2000) {
      addWarning(`Duplicate /api/admin/me request detected within ${timeDiff.toFixed(1)}ms`);
    }
  }
}

/**
 * Detect if /api/admin/me is called prematurely
 */
export function detectPrematureMeRequest(status: {
  firebaseUserExists: boolean;
  tokenExists: boolean;
  authInitializationComplete: boolean;
  requestSequence: number;
}) {
  if (!status.tokenExists) {
    addWarning(`/api/admin/me called before Firebase ID token was available`);
  }
}

/**
 * Export a fully sanitized JSON representation of the latest trace
 */
export function exportLatestTrace(): string {
  const latest = activeTrace || traceHistory[traceHistory.length - 1];
  if (!latest) return "{}";

  // Events are already sanitized when recorded, so we can serialize directly
  return JSON.stringify(latest, null, 2);
}

/**
 * Print a collapsed console summary of the current trace
 */
export function printConsoleSummary() {
  const latest = activeTrace || traceHistory[traceHistory.length - 1];
  if (!latest) return;

  const debugEnabled =
    import.meta.env.VITE_AUTH_PERFORMANCE_DEBUG === "true" ||
    import.meta.env.DEV;

  if (!debugEnabled) return;

  console.groupCollapsed(`[AuthPerformance] Trace ${latest.traceId}`);
  console.log("Trace Info:", {
    traceId: latest.traceId,
    warnings: latest.warnings,
    counts: latest.counts,
    backendTimings: latest.backendTimings,
  });

  console.table(
    latest.events.map((e) => ({
      Event: e.event,
      "Elapsed (ms)": e.elapsedMs.toFixed(1),
      "Duration (ms)": e.durationMs ? e.durationMs.toFixed(1) : "-",
      Status: e.status || "-",
    }))
  );

  // Find the slowest step
  let slowestEvent = "";
  let maxDuration = 0;
  latest.events.forEach((e) => {
    if (e.durationMs && e.durationMs > maxDuration) {
      maxDuration = e.durationMs;
      slowestEvent = e.event;
    }
  });

  if (slowestEvent) {
    console.log(
      `Slowest step: ${slowestEvent} — ${maxDuration.toFixed(1)} ms`
    );
    if (latest.warnings.length > 0) {
      console.log(`Possible concerns: ${latest.warnings.join("; ")}`);
    }
  }

  console.groupEnd();
}
