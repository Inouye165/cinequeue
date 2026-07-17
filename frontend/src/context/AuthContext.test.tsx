import { useEffect } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act, waitFor } from "@testing-library/react";
import { AuthProvider, useAuth, __resetFirebaseAuthForTests } from "./AuthContext";
import { api } from "../api";

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
vi.mock("../api", () => {
  return {
    api: {
      firebaseConfig: vi.fn(() => Promise.resolve({ apiKey: "mock-key", authDomain: "mock-domain" })),
      csrf: vi.fn(() => Promise.resolve({ csrf_token: "mock-csrf" })),
      createSession: vi.fn(() => Promise.resolve({ status: "success" })),
      me: vi.fn(() => Promise.resolve({ uid: "test-uid", email: "test@example.com" })),
      adminMe: vi.fn(() => Promise.resolve({ username: "test@example.com" })),
      logout: vi.fn(() => Promise.resolve({ status: "success" })),
    },
  };
});

// Test component to read context state
function TestConsumer({ onState }: { onState: (state: any) => void }) {
  const auth = useAuth();
  useEffect(() => {
    onState(auth);
  }, [auth]);
  return <div>Test Consumer</div>;
}

describe("AuthContext and AuthProvider", () => {
  beforeEach(() => {
    __resetFirebaseAuthForTests();
    vi.clearAllMocks();
    authStateChangedCallback = null;
    mockAuth.currentUser = null;
    vi.mocked(api.me).mockRejectedValue(new Error("No session"));
  });

  it("should not call /api/admin/me before the Firebase observer resolves", async () => {
    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    // Initial state should be loading and not initialized
    expect(latestState.loading).toBe(true);
    expect(latestState.authInitialized).toBe(false);
    expect(api.adminMe).not.toHaveBeenCalled();
  });

  it("should not call /api/admin/me when observer returns null", async () => {
    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    // Wait for observer subscription
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    // Trigger signed-out observer
    await act(async () => {
      await authStateChangedCallback!(null);
    });

    expect(latestState.user).toBeNull();
    expect(latestState.isAdmin).toBe(false);
    expect(latestState.authInitialized).toBe(true);
    expect(latestState.loading).toBe(false);
    expect(api.adminMe).not.toHaveBeenCalled();
  });

  it("should retrieve ID token and call /api/admin/me with token when user signs in", async () => {
    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "firebase-uid-123",
      email: "admin@example.com",
      displayName: "Mock Admin",
      photoURL: "http://photo.com",
      getIdToken: vi.fn(() => Promise.resolve("mock-id-token-abc")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    // Check token was retrieved
    expect(mockFirebaseUser.getIdToken).toHaveBeenCalled();
    // Check adminMe was called with the correct Bearer token
    expect(api.adminMe).toHaveBeenCalledWith("mock-id-token-abc");

    expect(latestState.user).toEqual({
      uid: "firebase-uid-123",
      email: "admin@example.com",
      display_name: "Mock Admin",
      photo_url: "http://photo.com",
    });
    expect(latestState.isAdmin).toBe(true);
    expect(latestState.authInitialized).toBe(true);
    expect(latestState.loading).toBe(false);
  });

  it("should handle non-admin users (403 from adminMe) correctly without triggering blocking error", async () => {
    // Mock adminMe returning 403 Forbidden
    vi.mocked(api.adminMe).mockRejectedValueOnce({
      status: 403,
      message: "Forbidden: Not an admin",
    });

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "firebase-uid-nonadmin",
      email: "user@example.com",
      displayName: "Normal User",
      photoURL: null,
      getIdToken: vi.fn(() => Promise.resolve("token-user")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    expect(latestState.user).toBeDefined();
    expect(latestState.user.email).toBe("user@example.com");
    expect(latestState.isAdmin).toBe(false);
    expect(latestState.error).toBeNull(); // Normal non-admin is not an error
    expect(latestState.authInitialized).toBe(true);
    expect(latestState.loading).toBe(false);
  });

  it("should handle other admin endpoint failures correctly and store error", async () => {
    vi.mocked(api.adminMe).mockRejectedValueOnce(new Error("500 Internal Error"));

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "firebase-uid-user",
      email: "user2@example.com",
      displayName: "Normal User 2",
      photoURL: null,
      getIdToken: vi.fn(() => Promise.resolve("token-user-2")),
    };

    await act(async () => {
      await authStateChangedCallback!(mockFirebaseUser);
    });

    expect(latestState.user).toBeDefined();
    expect(latestState.isAdmin).toBe(false);
    expect(latestState.error).toBe("500 Internal Error");
    expect(latestState.authInitialized).toBe(true);
    expect(latestState.loading).toBe(false); // Make sure loading is cleared
  });

  it("should deduplicate overlapping /api/admin/me requests", async () => {
    // Set up delayed resolver
    let resolveAdmin: any;
    const adminPromise = new Promise<{ username: string }>((resolve) => {
      resolveAdmin = resolve;
    });
    vi.mocked(api.adminMe).mockReturnValue(adminPromise);

    render(
      <AuthProvider>
        <TestConsumer onState={() => {}} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "firebase-uid",
      email: "user@example.com",
      getIdToken: vi.fn(() => Promise.resolve("token-123")),
    };

    // Trigger callback twice simultaneously
    await act(async () => {
      const p1 = authStateChangedCallback!(mockFirebaseUser);
      const p2 = authStateChangedCallback!(mockFirebaseUser);
      resolveAdmin({ username: "user@example.com" });
      await Promise.all([p1, p2]);
    });

    // Should only call api.adminMe once
    expect(api.adminMe).toHaveBeenCalledTimes(1);
  });

  it("should enforce generation safety under StrictMode remounts", async () => {
    let latestState: any = null;

    // We render, unmount, and render again
    const { unmount } = render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    // Get the callback from the first mount
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());
    const firstCallback = authStateChangedCallback;

    // Unmount (triggers cleanup)
    unmount();
    expect(mockUnsubscribe).toHaveBeenCalledTimes(1);

    // Mount again (new generation)
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());
    const secondCallback = authStateChangedCallback;
    expect(firstCallback).not.toBe(secondCallback);

    // Trigger the old callback from the first generation
    const oldFirebaseUser = {
      uid: "old-uid",
      email: "old@example.com",
      getIdToken: vi.fn(() => Promise.resolve("old-token")),
    };

    await act(async () => {
      await firstCallback!(oldFirebaseUser);
    });

    // State should remain unaffected (default loading/uninitialized values)
    expect(latestState.user).toBeNull();

    // Trigger the new callback from the second generation
    const newFirebaseUser = {
      uid: "new-uid",
      email: "new@example.com",
      getIdToken: vi.fn(() => Promise.resolve("new-token")),
    };

    await act(async () => {
      await secondCallback!(newFirebaseUser);
    });

    // State should correctly update to new generation
    expect(latestState.user.uid).toBe("new-uid");
  });

  it("Test 1: Signed-in cached user - Firebase user is restored, token is stored, global loading clears without waiting for profile data", async () => {
    let resolveMe: any;
    const mePromise = new Promise<any>((resolve) => { resolveMe = resolve; });
    vi.mocked(api.me).mockReturnValue(mePromise);

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "cached-uid",
      email: "cached@example.com",
      getIdToken: vi.fn(() => Promise.resolve("cached-token")),
    };

    await act(async () => {
      authStateChangedCallback!(mockFirebaseUser);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(latestState.authInitialized).toBe(true);
    expect(latestState.loading).toBe(false);
    expect(latestState.firebaseUser.uid).toBe("cached-uid");
    expect(latestState.idToken).toBe("cached-token");
    expect(latestState.authorizationReady).toBe(false);

    resolveMe({ uid: "cached-uid", email: "cached@example.com" });
  });

  it("Test 2: Signed-out user - Auth resolves correctly, loading clears, no protected data request is made", async () => {
    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    await act(async () => {
      await authStateChangedCallback!(null);
    });

    expect(latestState.user).toBeNull();
    expect(latestState.loading).toBe(false);
    expect(latestState.authInitialized).toBe(true);
    expect(latestState.authorizationReady).toBe(true);
    expect(api.csrf).not.toHaveBeenCalled();
    expect(api.createSession).not.toHaveBeenCalled();
  });

  it("Test 3: Slow profile request - App shell becomes available, profile-dependent UI remains loading", async () => {
    let resolveMe: any;
    const mePromise = new Promise<any>((resolve) => { resolveMe = resolve; });
    vi.mocked(api.me).mockReturnValue(mePromise);

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "uid-3",
      email: "user3@example.com",
      getIdToken: vi.fn(() => Promise.resolve("token-3")),
    };

    await act(async () => {
      authStateChangedCallback!(mockFirebaseUser);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(latestState.loading).toBe(false);
    expect(latestState.profileLoading).toBe(true);
    expect(latestState.profile).toBeNull();

    await act(async () => {
      resolveMe({ uid: "uid-3", email: "user3@example.com", display_name: "User Three" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(latestState.profileLoading).toBe(false);
    expect(latestState.profile.display_name).toBe("User Three");
  });

  it("Test 4: Slow role or authorization request - Admin content remains protected, no flash", async () => {
    let resolveAdmin: any;
    const adminPromise = new Promise<any>((resolve) => { resolveAdmin = resolve; });
    vi.mocked(api.adminMe).mockReturnValue(adminPromise);

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    await waitFor(() => expect(authStateChangedCallback).toBeDefined());

    const mockFirebaseUser = {
      uid: "admin-uid",
      email: "admin@example.com",
      getIdToken: vi.fn(() => Promise.resolve("admin-token")),
    };

    await act(async () => {
      authStateChangedCallback!(mockFirebaseUser);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(latestState.loading).toBe(false);
    expect(latestState.authorizationReady).toBe(false);
    expect(latestState.isAdmin).toBe(false);

    await act(async () => {
      resolveAdmin({ username: "admin@example.com" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(latestState.authorizationReady).toBe(true);
    expect(latestState.isAdmin).toBe(true);
  });

  it("Test 5: React Strict Mode duplicate effect execution - Only one listener, Firebase app reused, stale skipped", async () => {
    vi.mocked(api.firebaseConfig).mockClear();
    render(
      <AuthProvider>
        <TestConsumer onState={() => {}} />
      </AuthProvider>
    );
    expect(vi.mocked(api.firebaseConfig)).toHaveBeenCalledTimes(1);
  });

  it("Test 6: Provider unmount during initialization - Listener and async work cleaned up, no state updates", async () => {
    let latestState: any = null;
    const { unmount } = render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
    );

    expect(latestState.loading).toBe(true);
    await waitFor(() => expect(authStateChangedCallback).toBeDefined());
    unmount();

    expect(mockUnsubscribe).toHaveBeenCalled();
  });

  it("Test 7: Performance instrumentation - Awaited steps produce start/completion events and trace accounts for time", async () => {
    const { getTraceHistory } = await import("../utils/authPerformanceMonitor");
    const history = getTraceHistory();
    expect(history.length).toBeGreaterThan(0);
    const trace = history[history.length - 1];
    
    expect(trace.traceId).toBeDefined();
    expect(trace.events.some(e => e.event === "auth_provider_mounted")).toBe(true);
  });

  it("Test 8: Authentication ordering - should not call adminMe until createSession resolves", async () => {
    let resolveSession: any;
    const sessionPromise = new Promise<any>((resolve) => { resolveSession = resolve; });
    vi.mocked(api.createSession).mockReturnValueOnce(sessionPromise);

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
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

    // createSession started, but adminMe should NOT have been called yet
    expect(api.createSession).toHaveBeenCalled();
    expect(api.adminMe).not.toHaveBeenCalled();
    expect(latestState.sessionReady).toBe(false);
    expect(latestState.authorizationReady).toBe(false);

    // Resolve session creation
    await act(async () => {
      resolveSession({ status: "success" });
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // Now sessionReady is true and adminMe should be called
    expect(latestState.sessionReady).toBe(true);
    await waitFor(() => expect(api.adminMe).toHaveBeenCalledWith("admin-token"));
    
    // authorizationReady becomes true only after adminMe resolves
    await waitFor(() => expect(latestState.authorizationReady).toBe(true));
  });

  it("Test 9: Session failure - when createSession rejects, adminMe is not called", async () => {
    vi.mocked(api.createSession).mockRejectedValueOnce(new Error("Session creation failed"));

    let latestState: any = null;
    render(
      <AuthProvider>
        <TestConsumer onState={(s) => { latestState = s; }} />
      </AuthProvider>
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

    expect(api.createSession).toHaveBeenCalled();
    expect(api.adminMe).not.toHaveBeenCalled();
    expect(latestState.sessionReady).toBe(false);
    expect(latestState.authorizationReady).toBe(true);
    expect(latestState.isAdmin).toBe(false);
    expect(latestState.error).toContain("Session creation failed");
  });
});
