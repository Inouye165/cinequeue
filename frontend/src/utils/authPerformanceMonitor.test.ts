import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  generateTraceId,
  sanitizeDetails,
  startTrace,
  recordEvent,
  getTraceHistory,
  exportLatestTrace,
  detectDuplicateMeRequest,
  detectPrematureMeRequest,
} from "./authPerformanceMonitor";

describe("authPerformanceMonitor", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Clear global state if any by creating a fresh trace
  });

  it("should generate trace IDs in correct format", () => {
    const id = generateTraceId();
    expect(id).toMatch(/^auth-\d+-\w{4}$/);
  });

  it("should sanitize sensitive details", () => {
    const details = {
      apiKey: "AIzaSyAOlo4dMXfvW7Su",
      firebaseToken: "eyJhbGciOiJSUzI1NiIsImt...",
      password: "secret_password",
      username: "admin_user",
      cookieValue: "session_cookie_123",
      otherSafeField: "safe_value",
    };

    const sanitized = sanitizeDetails(details);
    expect(sanitized).toBeDefined();
    expect(sanitized!.apiKey).toBe("[REDACTED (length: 20)]");
    expect(sanitized!.firebaseToken).toBe("[REDACTED (length: 26)]");
    expect(sanitized!.password).toBe("[REDACTED (length: 15)]");
    expect(sanitized!.cookieValue).toBe("[REDACTED (length: 18)]");
    expect(sanitized!.otherSafeField).toBe("safe_value");
    expect(sanitized!.username).toBe("admin_user");
  });

  it("should calculate elapsed times and durations with mocked performance timers", () => {
    let mockTime = 100.0;
    vi.spyOn(performance, "now").mockImplementation(() => mockTime);

    // Start trace at 100ms
    const trace = startTrace();
    expect(trace.startTime).toBe(100.0);

    // Event 1 at 250ms (elapsed: 150ms)
    mockTime = 250.0;
    recordEvent("firebase_config_fetch_started", "start");
    
    // Event 2 at 400ms (elapsed: 300ms, duration of config fetch: 150ms)
    mockTime = 400.0;
    const completedEvent = recordEvent("firebase_config_fetch_completed", "success");

    expect(completedEvent).toBeDefined();
    expect(completedEvent!.elapsedMs).toBe(300.0);
    expect(completedEvent!.durationMs).toBe(150.0);
  });

  it("should maintain bounded trace storage (max 10)", () => {
    for (let i = 0; i < 15; i++) {
      startTrace();
    }
    const history = getTraceHistory();
    expect(history.length).toBeLessThanOrEqual(10);
  });

  it("should warning if /api/admin/me is called before a token is available", () => {
    const trace = startTrace();
    const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    detectPrematureMeRequest({
      firebaseUserExists: false,
      tokenExists: false,
      authInitializationComplete: true,
      requestSequence: 1,
    });

    expect(trace.warnings.length).toBe(1);
    expect(trace.warnings[0]).toContain("called before Firebase ID token was available");
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it("should warn about duplicate requests within 2 seconds", () => {
    let mockTime = 1000.0;
    vi.spyOn(performance, "now").mockImplementation(() => mockTime);
    const trace = startTrace();
    const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    // First request
    mockTime = 1200.0;
    recordEvent("admin_me_request_started", "start");
    detectDuplicateMeRequest();

    // Duplicate request after 500ms
    mockTime = 1700.0;
    recordEvent("admin_me_request_started", "start");
    detectDuplicateMeRequest();

    expect(trace.warnings.length).toBe(1);
    expect(trace.warnings[0]).toContain("Duplicate /api/admin/me request detected");
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it("should export a sanitized trace representation", () => {
    startTrace();
    recordEvent("test_event", "success", {
      apiKey: "secretKey123",
      safeFieldName: "safeDetailsValue",
    });

    const exported = exportLatestTrace();
    expect(exported).not.toContain("secretKey123");
    expect(exported).toContain("[REDACTED (length: 12)]");
    expect(exported).toContain("safeDetailsValue");
  });
});
