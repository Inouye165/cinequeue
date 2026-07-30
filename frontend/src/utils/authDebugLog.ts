/**
 * Auth Debug Logger — timestamped, in-memory + console logging for diagnosing
 * the "Verifying session…" spinner hang.
 *
 * Every entry captures:
 *   - ISO wall-clock timestamp
 *   - Elapsed ms since the very first log entry (session-relative)
 *   - Delta ms since the previous log entry
 *   - A human-readable label and optional detail payload
 *
 * Entries are kept in a bounded ring buffer (max 500) and are accessible from
 * the admin dashboard via getAuthDebugLogs().
 */

export interface AuthDebugEntry {
  /** Sequential index (1-based) */
  seq: number;
  /** ISO-8601 wall-clock time */
  iso: string;
  /** Milliseconds since first entry in this page session */
  elapsedMs: number;
  /** Milliseconds since the previous entry */
  deltaMs: number;
  /** Log severity */
  level: "debug" | "info" | "warn" | "error";
  /** Human-readable label, e.g. "firebase_config_fetch_start" */
  label: string;
  /** Optional structured detail payload (never contains secrets) */
  detail?: Record<string, unknown>;
}

const MAX_ENTRIES = 500;
let entries: AuthDebugEntry[] = [];
let seq = 0;
let firstTimestamp: number | null = null;
let lastTimestamp: number | null = null;

/** Listeners notified on every new entry (used by React components to re-render). */
type Listener = () => void;
const listeners = new Set<Listener>();

export function subscribeAuthDebugLog(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notifyListeners() {
  setTimeout(() => {
    listeners.forEach((fn) => fn());
  }, 0);
}

/**
 * Sanitize details — strip anything that looks like a token/key/password.
 */
function sanitize(detail?: Record<string, unknown>): Record<string, unknown> | undefined {
  if (!detail) return undefined;
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(detail)) {
    const lower = k.toLowerCase();
    if (
      lower.includes("token") ||
      lower.includes("key") ||
      lower.includes("password") ||
      lower.includes("cookie") ||
      lower.includes("secret") ||
      lower.includes("credential")
    ) {
      clean[k] = typeof v === "string" ? `[REDACTED len=${v.length}]` : "[REDACTED]";
    } else {
      clean[k] = v;
    }
  }
  return clean;
}

function pushEntry(
  level: AuthDebugEntry["level"],
  label: string,
  detail?: Record<string, unknown>,
): AuthDebugEntry {
  const now = performance.now();
  if (firstTimestamp === null) firstTimestamp = now;

  const elapsedMs = now - firstTimestamp;
  const deltaMs = lastTimestamp === null ? 0 : now - lastTimestamp;
  lastTimestamp = now;

  seq++;
  const entry: AuthDebugEntry = {
    seq,
    iso: new Date().toISOString(),
    elapsedMs: Math.round(elapsedMs * 10) / 10,
    deltaMs: Math.round(deltaMs * 10) / 10,
    level,
    label,
    detail: sanitize(detail),
  };

  entries.push(entry);
  if (entries.length > MAX_ENTRIES) {
    entries = entries.slice(-MAX_ENTRIES);
  }

  // Console output — always, regardless of debug env var, since we're diagnosing a hang.
  const tag = `[AuthDebug +${entry.elapsedMs.toFixed(0)}ms Δ${entry.deltaMs.toFixed(0)}ms]`;
  const consoleFn =
    level === "error"
      ? console.error
      : level === "warn"
        ? console.warn
        : console.log;
  if (entry.detail) {
    consoleFn(tag, label, entry.detail);
  } else {
    consoleFn(tag, label);
  }

  notifyListeners();
  return entry;
}

/* ── Public API ──────────────────────────────────────────────────────── */

export const authLog = {
  debug: (label: string, detail?: Record<string, unknown>) => pushEntry("debug", label, detail),
  info: (label: string, detail?: Record<string, unknown>) => pushEntry("info", label, detail),
  warn: (label: string, detail?: Record<string, unknown>) => pushEntry("warn", label, detail),
  error: (label: string, detail?: Record<string, unknown>) => pushEntry("error", label, detail),
};

/** Return a *copy* of the current log buffer (newest last). */
export function getAuthDebugLogs(): AuthDebugEntry[] {
  return [...entries];
}

/** Clear all stored entries (e.g. on logout). */
export function clearAuthDebugLogs(): void {
  entries = [];
  seq = 0;
  firstTimestamp = null;
  lastTimestamp = null;
  notifyListeners();
}
