import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  Auth as FirebaseAuth
} from "firebase/auth";
import { api } from "../api";
import {
  startTrace,
  recordEvent,
  incrementCount,
} from "../utils/authPerformanceMonitor";
import { authLog } from "../utils/authDebugLog";

export interface UserInfo {
  uid: string;
  email: string;
  display_name: string | null;
  photo_url: string | null;
}

interface AuthContextType {
  user: UserInfo | null;
  isAdmin: boolean;
  authInitialized: boolean;
  loading: boolean;
  error: string | null;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  refreshAdminState: () => Promise<void>;

  // New explicit states
  authReady: boolean;
  firebaseUser: UserInfo | null;
  idToken: string | null;
  profileLoading: boolean;
  profile: any | null;
  roleLoading: boolean;
  role: string | null;
  authorizationReady: boolean;
  sessionReady: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

let firebaseAuthInstance: FirebaseAuth | null = null;
let firebaseAuthPromise: Promise<FirebaseAuth> | null = null;

async function getFirebaseAuth(): Promise<FirebaseAuth> {
  if (firebaseAuthInstance) {
    authLog.debug("getFirebaseAuth: reusing cached instance");
    recordEvent("firebase_app_reused", "success");
    recordEvent("firebase_auth_instance_ready", "success");
    return firebaseAuthInstance;
  }

  if (firebaseAuthPromise) {
    authLog.debug("getFirebaseAuth: awaiting existing init promise");
    return firebaseAuthPromise;
  }

  authLog.info("getFirebaseAuth: starting fresh initialization");
  firebaseAuthPromise = (async () => {
    incrementCount("configFetches");
    recordEvent("firebase_config_fetch_started", "start");
    authLog.info("fetching /api/auth/config…");
    const config = await api.firebaseConfig();
    authLog.info("firebase config received", { projectId: config.projectId, authDomain: config.authDomain });
    recordEvent("firebase_config_fetch_completed", "success");
    
    if (!config || !config.apiKey) {
      authLog.error("firebase config missing apiKey!");
      throw new Error("Firebase API key is missing or empty. Please verify your backend .env file contains FIREBASE_API_KEY and restart the backend server.");
    }
    
    let app;
    incrementCount("initAttempts");
    recordEvent("firebase_initialization_started", "start");
    if (getApps().length === 0) {
      authLog.info("initializeApp: creating new Firebase app");
      app = initializeApp(config);
      recordEvent("firebase_app_created", "success");
    } else {
      authLog.info("initializeApp: reusing existing Firebase app");
      app = getApp();
      recordEvent("firebase_app_reused", "success");
    }
    recordEvent("firebase_initialization_completed", "success");
    
    firebaseAuthInstance = getAuth(app);
    authLog.info("firebase Auth instance created");
    recordEvent("firebase_auth_instance_ready", "success");
    return firebaseAuthInstance;
  })();

  try {
    return await firebaseAuthPromise;
  } catch (err) {
    authLog.error("getFirebaseAuth FAILED", { error: (err as Error).message });
    firebaseAuthPromise = null;
    throw err;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [authInitialized, setAuthInitialized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New explicit states
  const [authReady, setAuthReady] = useState(false);
  const [firebaseUser, setFirebaseUser] = useState<UserInfo | null>(null);
  const [idToken, setIdToken] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profile, setProfile] = useState<any | null>(null);
  const [roleLoading, setRoleLoading] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [authorizationReady, setAuthorizationReady] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);

  const providerInstanceId = useRef(Math.random().toString(36).substring(2, 6));
  const unsubscribeRef = useRef<(() => void) | null>(null);
  
  const generationRef = useRef(0);
  const adminMePromiseRef = useRef<Promise<any> | null>(null);

  const fetchAdminMe = async (token: string): Promise<{ username: string }> => {
    if (adminMePromiseRef.current) {
      recordEvent("admin_me_request_deduplicated", "success");
      return adminMePromiseRef.current;
    }
    const promise = api.adminMe(token);
    adminMePromiseRef.current = promise;
    try {
      return await promise;
    } finally {
      adminMePromiseRef.current = null;
    }
  };

  useEffect(() => {
    let active = true;
    const generation = ++generationRef.current;
    const isCurrent = () => active && generation === generationRef.current;

    startTrace();
    incrementCount("mounts");
    recordEvent("auth_provider_mounted", "success", { instanceId: providerInstanceId.current, generation });
    authLog.info("AuthProvider mounted", { instanceId: providerInstanceId.current, generation });

    const initializeAuth = async () => {
      authLog.info("initializeAuth: setting loading=true");
      recordEvent("auth_context_state_update_started", "start");
      setLoading(true);
      setError(null);
      recordEvent("auth_context_state_update_completed", "success");

      try {
        authLog.info("initializeAuth: calling getFirebaseAuth()");
        const auth = await getFirebaseAuth();
        authLog.info("initializeAuth: getFirebaseAuth() resolved");
        if (!isCurrent()) {
          authLog.warn("initializeAuth: stale generation after getFirebaseAuth", { generation, current: generationRef.current });
          recordEvent("auth_generation_stale", "skipped", { generation, current: generationRef.current });
          return;
        }

        if (!unsubscribeRef.current) {
          incrementCount("listenersRegistered");
          authLog.info("initializeAuth: registering onIdTokenChanged listener");
          
          const unsubscribe = auth.onIdTokenChanged(async (firebaseUser) => {
            recordEvent("auth_state_callback_started", "start");
            incrementCount("callbacks");
            authLog.info("onIdTokenChanged fired", { hasUser: !!firebaseUser });

            if (!isCurrent()) {
              authLog.warn("onIdTokenChanged: stale generation, skipping");
              recordEvent("auth_state_callback_stale", "skipped", { generation, current: generationRef.current });
              return;
            }

            if (firebaseUser) {
              authLog.info("onIdTokenChanged: user present", { uid: firebaseUser.uid, email: firebaseUser.email });
              recordEvent("auth_state_user_available", "success", { uid: firebaseUser.uid, email: firebaseUser.email });
              
              try {
                incrementCount("getIdTokenCalls");
                recordEvent("id_token_request_started", "start");
                authLog.info("calling firebaseUser.getIdToken()…");
                const token = await firebaseUser.getIdToken();
                authLog.info("getIdToken() resolved", { tokenLength: token.length });
                recordEvent("id_token_request_completed", "success");

                if (!isCurrent()) {
                  authLog.warn("stale generation after getIdToken");
                  return;
                }

                const uInfo: UserInfo = {
                  uid: firebaseUser.uid,
                  email: firebaseUser.email ?? "",
                  display_name: firebaseUser.displayName ?? null,
                  photo_url: firebaseUser.photoURL ?? null
                };

                // Fast Auth Resolution: set core state immediately and clear global loading!
                authLog.info("setting fast-auth states: authInitialized=true, authorizationReady=false");
                recordEvent("auth_context_state_update_started", "start");
                setFirebaseUser(uInfo);
                setIdToken(token);
                setAuthReady(true);
                setAuthInitialized(true);
                setSessionReady(false);
                setRoleLoading(true);
                setProfileLoading(true);
                setAuthorizationReady(false);
                recordEvent("auth_context_state_update_completed", "success");

                const performAuthSequence = async () => {
                  try {
                    // Pre-check: decode JWT auth_time client-side to avoid slow backend rejection
                    // If the cached Firebase session is stale (> 5 min), sign out immediately.
                    try {
                      const payloadPart = token.split(".")[1];
                      const decoded = JSON.parse(atob(payloadPart));
                      const authTime = decoded.auth_time;
                      if (authTime) {
                        const ageSeconds = Math.floor(Date.now() / 1000) - authTime;
                        authLog.info("auth_time pre-check", { authTime, ageSeconds, maxAge: 300 });
                        if (ageSeconds > 5 * 60) {
                          authLog.warn(
                            `auth_time is ${ageSeconds}s old (${(ageSeconds / 86400).toFixed(1)} days) — ` +
                            "stale cached session, signing out immediately"
                          );
                          // Sign out without showing error — user just needs to click login again
                          setAuthorizationReady(true);
                          setLoading(false);
                          setUser(null);
                          setFirebaseUser(null);
                          setIdToken(null);
                          setSessionReady(false);
                          setRoleLoading(false);
                          setProfileLoading(false);
                          setAuthInitialized(true);
                          try { await firebaseSignOut(auth); } catch (_) { /* ignore */ }
                          return;
                        }
                      }
                    } catch (preErr) {
                      authLog.debug("auth_time pre-check failed (non-fatal)", { error: (preErr as Error).message });
                    }

                    authLog.info("performAuthSequence: requesting CSRF token…");
                    recordEvent("csrf_request_started", "start");
                    const csrfData = await api.csrf();
                    authLog.info("performAuthSequence: CSRF token received");
                    recordEvent("csrf_request_completed", "success");
                    if (!isCurrent()) { authLog.warn("stale after CSRF"); return; }

                    authLog.info("performAuthSequence: calling createSession…");
                    recordEvent("session_creation_started", "start");
                    await api.createSession(token, csrfData.csrf_token);
                    authLog.info("performAuthSequence: createSession succeeded");
                    recordEvent("session_creation_completed", "success");
                    if (!isCurrent()) { authLog.warn("stale after createSession"); return; }

                    authLog.info("performAuthSequence: setting sessionReady=true, loading=false");
                    setSessionReady(true);
                    setUser(uInfo);
                    setLoading(false);
                    setError(null);
                    recordEvent("auth_loading_cleared", "success");

                    // Set profile immediately from Firebase user data — no need to wait
                    // for /api/auth/me which uses the session cookie and may hit clock-skew sleep.
                    authLog.info("performAuthSequence: setting profile from Firebase data (non-blocking)");
                    setProfile({
                      uid: uInfo.uid,
                      email: uInfo.email,
                      display_name: uInfo.display_name ?? null,
                      photo_url: uInfo.photo_url ?? null
                    });
                    setProfileLoading(false);

                    // Start admin role check (uses Bearer token, not session cookie — fast)
                    authLog.info("performAuthSequence: starting adminMe role check");
                    const rolePromise = fetchAdminMe(token)
                      .then(() => {
                        authLog.info("adminMe resolved: isAdmin=true");
                        recordEvent("admin_me_request_completed", "success");
                        if (!isCurrent()) return { isAdmin: true, role: "admin", error: null };
                        setIsAdmin(true);
                        setRole("admin");
                        setRoleLoading(false);
                        return { isAdmin: true, role: "admin", error: null };
                      })
                      .catch((err: any) => {
                        authLog.warn("adminMe failed", { error: err.message, status: err.status });
                        recordEvent("admin_me_request_failed", "failure", { error: err.message });
                        if (!isCurrent()) return { isAdmin: false, role: null, error: err.message };
                        const isForbidden =
                          err.status === 403 ||
                          err.message?.includes("403") ||
                          err.message?.toLowerCase().includes("not authorized") ||
                          err.message?.toLowerCase().includes("forbidden");
                        setIsAdmin(false);
                        setRole(isForbidden ? "user" : null);
                        setRoleLoading(false);
                        return {
                          isAdmin: false,
                          role: isForbidden ? "user" : null,
                          error: isForbidden ? null : (err.message || "Failed to resolve admin verification")
                        };
                      });

                    authLog.info("performAuthSequence: awaiting rolePromise only (profile set from Firebase data)…");
                    const roleResult = await rolePromise;
                    authLog.info("performAuthSequence: role resolved", { roleError: roleResult.error || null });
                    if (!isCurrent()) return;

                    recordEvent("auth_context_state_update_started", "start");
                    if (roleResult.error) {
                      setError(roleResult.error);
                    }
                    recordEvent("authorization_ready", "success");
                    setAuthorizationReady(true);
                    authLog.info("performAuthSequence: COMPLETE — authorizationReady=true");
                    recordEvent("auth_context_state_update_completed", "success");
                    recordEvent("auth_state_callback_completed", "success");
                    recordEvent("auth_trace_completed", "success");

                    // Background: verify session cookie works by calling /api/auth/me
                    // This is non-blocking — user already sees the dashboard.
                    // If it fails, the next real API call will catch the issue.
                    authLog.info("performAuthSequence: starting background session cookie verification (/api/auth/me)");
                    recordEvent("profile_request_started", "start");
                    api.me().then((pData) => {
                      authLog.info("background profile verification succeeded", { email: pData.email });
                      recordEvent("profile_request_completed", "success");
                      if (!isCurrent()) return;
                      // Update profile with server-verified data
                      setProfile({
                        uid: pData.uid,
                        email: pData.email,
                        display_name: pData.display_name ?? null,
                        photo_url: pData.photo_url ?? null
                      });
                    }).catch((profileErr: any) => {
                      authLog.warn("background profile verification failed (non-fatal)", { error: profileErr.message });
                      recordEvent("profile_request_failed", "failure", { error: profileErr.message });
                    });

                  } catch (err: any) {
                    if (!isCurrent()) return;
                    
                    const errMsg = err.message || "Session or role resolution failed";
                    authLog.error("performAuthSequence FAILED", { error: errMsg });
                    recordEvent("auth_context_state_update_started", "start");
                    setError(errMsg);
                    setUser(null);
                    setFirebaseUser(null);
                    setIdToken(null);
                    setSessionReady(false);
                    setIsAdmin(false);
                    setRole(null);
                    setRoleLoading(false);
                    setProfileLoading(false);
                    setLoading(false);
                    recordEvent("authorization_ready", "failure");
                    setAuthorizationReady(true);
                    
                    try {
                      authLog.info("signing out of Firebase after auth sequence failure");
                      await firebaseSignOut(auth);
                    } catch (soErr) {
                      authLog.error("Firebase signout on failure also failed", { error: (soErr as Error).message });
                      console.error("Firebase signout on session creation failure failed:", soErr);
                    }

                    // Preserve error message after signout triggers state callback
                    setError(errMsg);

                    recordEvent("auth_context_state_update_completed", "success");
                    recordEvent("auth_state_callback_completed", "success");
                    recordEvent("auth_trace_completed", "success");
                  }
                };

                void performAuthSequence();

              } catch (err: any) {
                if (!isCurrent()) return;
                const errMsg = err.message || "Failed to resolve authentication";
                authLog.error("getIdToken / user-present block FAILED", { error: errMsg });
                recordEvent("auth_context_state_update_started", "start");
                setError(errMsg);
                setUser(null);
                setFirebaseUser(null);
                setIdToken(null);
                setAuthInitialized(true);
                setLoading(false);
                setAuthorizationReady(true);
                try {
                  await firebaseSignOut(auth);
                } catch (soErr) {
                  // ignore
                }
                setError(errMsg);
                recordEvent("auth_trace_completed", "success");
              }
            } else {
              authLog.info("onIdTokenChanged: NO user (signed out or first load with no session)");
              recordEvent("auth_state_no_user", "success");
              if (!isCurrent()) return;

              recordEvent("auth_context_state_update_started", "start");
              setFirebaseUser(null);
              setIdToken(null);
              setAuthReady(true);
              setUser(null);
              setIsAdmin(false);
              setRole(null);
              setProfile(null);
              setSessionReady(false);
              setRoleLoading(false);
              setProfileLoading(false);
              setAuthorizationReady(true);
              setAuthInitialized(true);
              setLoading(false);
              authLog.info("no-user path: authInitialized=true, loading=false, authorizationReady=true");
              recordEvent("auth_context_state_update_completed", "success");
              recordEvent("auth_state_callback_completed", "success");
              recordEvent("auth_loading_cleared", "success");
              recordEvent("auth_trace_completed", "success");
            }
          });

          unsubscribeRef.current = unsubscribe;
          recordEvent("auth_state_listener_registered", "success");
        }

        // The onIdTokenChanged observer handles initial state resolution and session creation universally across all environments.

      } catch (err: any) {
        if (!isCurrent()) return;
        authLog.error("initializeAuth TOP-LEVEL CATCH", { error: err.message });
        recordEvent("auth_context_state_update_started", "start");
        setError(err.message || "Authentication initialization failed");
        setUser(null);
        setFirebaseUser(null);
        setAuthInitialized(true);
        setLoading(false);
        setAuthReady(true);
        setAuthorizationReady(true);
        recordEvent("auth_context_state_update_completed", "success");
      }
    };

    void initializeAuth();

    return () => {
      active = false;
      incrementCount("cleanups");
      recordEvent("auth_provider_cleaned_up", "success", { instanceId: providerInstanceId.current, generation });
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
        recordEvent("auth_state_listener_unsubscribed", "success");
      }
    };
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      setIsAdmin(false);
      setAuthorizationReady(true);
      setLoading(false);
    };
    window.addEventListener("cinequeue-unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("cinequeue-unauthorized", handleUnauthorized);
    };
  }, []);

  const loginWithGoogle = async () => {
    authLog.info("loginWithGoogle: starting");
    startTrace();
    recordEvent("auth_context_state_update_started", "start");
    setError(null);
    setLoading(true);
    recordEvent("auth_context_state_update_completed", "success");
    
    const coopReferrer = document.referrer || "unknown";

    try {
      authLog.info("loginWithGoogle: getting firebase auth instance");
      const auth = await getFirebaseAuth();
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      
      incrementCount("popupLogins");
      recordEvent("popup_login_started", "start");
      authLog.info("loginWithGoogle: opening popup…");
      const userCredential = await signInWithPopup(auth, provider);
      authLog.info("loginWithGoogle: popup returned user", { uid: userCredential.user.uid, email: userCredential.user.email });
      recordEvent("popup_login_completed", "success", { uid: userCredential.user.uid });
      authLog.info("loginWithGoogle: popup complete — onIdTokenChanged will fire next");
    } catch (err: any) {
      authLog.error("loginWithGoogle: popup FAILED", { code: err.code, message: err.message });
      console.error("Popup login failed:", err);
      recordEvent("popup_login_failed", "failure", {
        code: err.code,
        message: err.message,
        coopReferrer,
      });
      let msg = "Google Sign-In failed. Please try again.";
      if (err.code === "auth/popup-blocked") {
        msg = "Sign-in popup was blocked by your browser. Please enable popups for this site.";
      } else if (err.code === "auth/popup-closed-by-user") {
        msg = "Sign-in popup was closed before completion.";
      } else if (err.code === "auth/unauthorized-domain") {
        msg = "This domain is not authorized in Firebase Console. Please add your Cloud Run URL to Firebase Authorized Domains.";
      }
      
      recordEvent("auth_context_state_update_started", "start");
      setError(msg);
      setLoading(false);
      recordEvent("auth_context_state_update_completed", "success");
    }
  };

  const logout = async () => {
    startTrace();
    recordEvent("auth_context_state_update_started", "start");
    setError(null);
    setLoading(true);
    recordEvent("auth_context_state_update_completed", "success");
    try {
      const auth = await getFirebaseAuth();
      await firebaseSignOut(auth);
      
      const csrfData = await api.csrf();
      await api.logout(csrfData.csrf_token);
    } catch (err) {
      console.error("Sign out action failed:", err);
    } finally {
      recordEvent("auth_context_state_update_started", "start");
      setUser(null);
      setFirebaseUser(null);
      setIdToken(null);
      setIsAdmin(false);
      setRole(null);
      setProfile(null);
      setSessionReady(false);
      setRoleLoading(false);
      setProfileLoading(false);
      setAuthorizationReady(true);
      setLoading(false);
      recordEvent("auth_context_state_update_completed", "success");
      recordEvent("auth_state_callback_completed", "success");
      recordEvent("auth_loading_cleared", "success");
      recordEvent("auth_trace_completed", "success");
    }
  };

  const refreshAdminState = async () => {
    const auth = await getFirebaseAuth();
    const currentUser = auth.currentUser;
    if (currentUser) {
      setLoading(true);
      try {
        const token = await currentUser.getIdToken(true);
        const csrfData = await api.csrf();
        await api.createSession(token, csrfData.csrf_token);
        setSessionReady(true);
        await fetchAdminMe(token);
        setIsAdmin(true);
      } catch (err: any) {
        setSessionReady(false);
        setIsAdmin(false);
        const isForbidden = err.message?.includes("403") || err.status === 403;
        if (!isForbidden) {
          setError(err.message || "Failed to refresh admin verification");
        }
      } finally {
        setLoading(false);
      }
    }
  };

  const clearError = () => setError(null);

  return (
    <AuthContext.Provider value={{
      user,
      isAdmin,
      authInitialized,
      loading,
      error,
      loginWithGoogle,
      logout,
      clearError,
      refreshAdminState,
      authReady,
      firebaseUser,
      idToken,
      profileLoading,
      profile,
      roleLoading,
      role,
      authorizationReady,
      sessionReady
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function __resetFirebaseAuthForTests() {
  firebaseAuthInstance = null;
  firebaseAuthPromise = null;
}
