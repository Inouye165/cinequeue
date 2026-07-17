import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import App from "./App";
import { api } from "./api";

// Mock Firebase APIs
const mockUnsubscribe = vi.fn();
let authStateChangedCallback: ((user: any) => Promise<void>) | null = null;

const mockAuth = {
  onIdTokenChanged: vi.fn((cb) => {
    authStateChangedCallback = cb;
    return mockUnsubscribe;
  }),
  currentUser: null as any,
};

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(),
  getApps: vi.fn(() => []),
  getApp: vi.fn(),
}));

vi.mock("firebase/auth", () => {
  return {
    getAuth: vi.fn(() => mockAuth),
    GoogleAuthProvider: class {},
    signInWithPopup: vi.fn(() => Promise.resolve({
      user: {
        uid: "test-uid",
        email: "test@example.com",
        getIdToken: vi.fn(() => Promise.resolve("test-firebase-token")),
      },
    })),
    signInWithRedirect: vi.fn(() => Promise.resolve()),
    getRedirectResult: vi.fn(() => Promise.resolve(null)),
    signOut: vi.fn(() => Promise.resolve()),
  };
});

// Mock api calls
vi.mock("./api", () => {
  return {
    api: {
      firebaseConfig: vi.fn(() => Promise.resolve({ apiKey: "mock-key", authDomain: "mock-domain" })),
      csrf: vi.fn(() => Promise.resolve({ csrf_token: "mock-csrf" })),
      createSession: vi.fn(() => Promise.resolve({ status: "success" })),
      me: vi.fn(() => Promise.resolve({ uid: "test-uid", email: "test@example.com" })),
      adminMe: vi.fn(() => Promise.resolve({ username: "admin@example.com" })),
      adminRequests: vi.fn(() => Promise.resolve({ approvals: [{ email: "user@example.com", status: "pending" }] })),
      adminLoginLogs: vi.fn(() => Promise.resolve({ logs: [] })),
      logout: vi.fn(() => Promise.resolve({ status: "success" })),
    },
  };
});

describe("App Authentication Gating & Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authStateChangedCallback = null;
    mockAuth.currentUser = null;
    vi.mocked(api.me).mockResolvedValue({ uid: "test-uid", email: "admin@example.com" });
    vi.mocked(api.adminMe).mockResolvedValue({ username: "admin@example.com" });
    vi.mocked(api.createSession).mockResolvedValue({ status: "success" });
    vi.mocked(api.csrf).mockResolvedValue({ csrf_token: "mock-csrf" });
    vi.mocked(api.adminRequests).mockResolvedValue({ approvals: [] });
    vi.mocked(api.adminLoginLogs).mockResolvedValue({ logs: [] });
  });

  it("Gating test: should NOT call adminRequests when Firebase auth is unresolved or no user is signed in", async () => {
    render(<App />);

    // Initial mount, loading state
    expect(api.adminRequests).not.toHaveBeenCalled();

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    // Trigger signed-out observer
    await act(async () => {
      await authStateChangedCallback!(null);
    });

    // Should still not call adminRequests because user is null
    expect(api.adminRequests).not.toHaveBeenCalled();
  });

  it("Gating test: should NOT call adminRequests when session is not ready", async () => {
    // Hold session creation unresolved
    let resolveSession: any;
    const sessionPromise = new Promise<any>((resolve) => { resolveSession = resolve; });
    vi.mocked(api.createSession).mockReturnValueOnce(sessionPromise);

    render(<App />);
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    // Session is not resolved yet, so sessionReady is false
    expect(api.adminRequests).not.toHaveBeenCalled();

    // Resolve session
    await act(async () => {
      resolveSession({ status: "success" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Still needs to complete adminMe to verify is admin
    await waitFor(() => expect(api.adminMe).toHaveBeenCalled());
    
    // Once adminMe completes, adminRequests should be called
    await waitFor(() => expect(api.adminRequests).toHaveBeenCalled());
  });

  it("Slow authorization test: should NOT call adminRequests and only show loading if adminMe is slow", async () => {
    // Session resolves but adminMe is held unresolved
    let resolveAdminMe: any;
    const adminMePromise = new Promise<any>((resolve) => { resolveAdminMe = resolve; });
    vi.mocked(api.adminMe).mockReturnValueOnce(adminMePromise);

    render(<App />);
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    // Since adminMe is slow, authorizationReady remains false
    expect(api.adminRequests).not.toHaveBeenCalled();

    // Resolve adminMe
    await act(async () => {
      resolveAdminMe({ username: "admin@example.com" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now it should proceed
    await waitFor(() => expect(api.adminRequests).toHaveBeenCalled());
  });

  it("Logout test: should clear admin request data and user state when logged out", async () => {
    render(<App />);
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    // Log in
    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    await waitFor(() => expect(api.adminRequests).toHaveBeenCalled());

    // Trigger logout
    await act(async () => {
      await authStateChangedCallback!(null);
    });

    // Wait for state updates to settle
    await waitFor(() => {
      expect(api.adminRequests).toHaveBeenCalledTimes(1); // Not called again
    });
  });

  it("Profile failure test: should remain logged in and query admin requests even if profile query fails", async () => {
    // Mock profile query (api.me) to fail
    vi.mocked(api.me).mockRejectedValueOnce(new Error("Profile fetch failed"));

    render(<App />);
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    // Even though profile failed, authorizationReady becomes true because role resolved successfully
    await waitFor(() => expect(api.adminRequests).toHaveBeenCalled());
  });

  it("Strict Mode test: does not duplicate requests for same generation", async () => {
    // Under React Strict Mode double-effect/mount triggers, verify no duplication
    render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    await waitFor(() => expect(api.adminRequests).toHaveBeenCalled());
    
    // The request should only run once successfully (or be aborted/re-run cleanly)
    // without duplicating concurrent unresolved requests.
    expect(api.createSession).toHaveBeenCalledTimes(1);
    expect(api.adminMe).toHaveBeenCalledTimes(1);
  });
});
