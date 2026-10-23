import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  Auth as FirebaseAuth
} from "firebase/auth";
import { api, type UserMe } from "../api";
import {
  startTrace,
  recordEvent,
  incrementCount,
} from "../utils/authPerformanceMonitor";
import { authLog } from "../utils/authDebugLog";
import { syncService } from "../services/syncService";
import { setAuthToken } from "../utils/authTokenStore";

export interface UserInfo {
  uid: string;
  email: string;
  display_name: string | null;
  photo_url: string | null;
}

interface AuthContextType {
  localOwnerId: string;
  useDeviceWorkspace: () => void;
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
    let cachedConfig: any = null;
    try {
      const raw = localStorage.getItem("cinequeue_firebase_config");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.apiKey) cachedConfig = parsed;
      }
    } catch {
      cachedConfig = null;
    }

    let config = cachedConfig;
    if (cachedConfig) {
      void api.firebaseConfig()
        .then((fresh) => {
          if (fresh && fresh.apiKey) {
            try { localStorage.setItem("cinequeue_firebase_config", JSON.stringify(fresh)); } catch {}
          }
        })
        .catch(() => {});
    } else {
      config = await api.firebaseConfig();
      if (config && config.apiKey) {
        try { localStorage.setItem("cinequeue_firebase_config", JSON.stringify(config)); } catch {}
      }
    }
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
  const [localOwnerId, setLocalOwnerId] = useState(() => localStorage.getItem("cinequeue_local_owner") || "guest_local");
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
  const authSequenceRef = useRef(0);
  const adminMePromiseRef = useRef<Promise<any> | null>(null);

  const fetchAdminMe = async (token: string): Promise<{ username: string; is_admin?: boolean }> => {
    if (adminMePromiseRef.current) {
      recordEvent("admin_me_request_deduplicated", "success");
      return adminMePromiseRef.current;
    }
    const promise = api.adminMe(token);
    adminMePromiseRef.current = promise;
    try {
      return await promise;
    } finally {
      if (adminMePromiseRef.current === promise) adminMePromiseRef.current = null;
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
          authLog.debug("initializeAuth: stale generation after getFirebaseAuth", { generation, current: generationRef.current });
          recordEvent("auth_generation_stale", "skipped", { generation, current: generationRef.current });
          return;
        }

        if (!unsubscribeRef.current) {
          incrementCount("listenersRegistered");
          authLog.info("initializeAuth: registering onIdTokenChanged listener");
          
          const unsubscribe = auth.onIdTokenChanged(async (firebaseUser) => {
            if (!active || generation !== generationRef.current) return;
            if (firebaseUser && localStorage.getItem("cinequeue_device_only") === "true") {
              setAuthReady(true);
              setAuthInitialized(true);
              setAuthorizationReady(true);
              setLoading(false);
              return;
            }
            const sequence = ++authSequenceRef.current;
            const isCurrent = () => active && generation === generationRef.current && sequence === authSequenceRef.current;
            syncService.setAuthenticatedOwner(null);
            adminMePromiseRef.current = null;
            setSessionReady(false);
            setUser(null);
            setIsAdmin(false);
            recordEvent("auth_state_callback_started", "start");
            incrementCount("callbacks");
            authLog.info("onIdTokenChanged fired", { hasUser: !!firebaseUser });

            if (!isCurrent()) {
              authLog.debug("onIdTokenChanged: stale generation, skipping");
              recordEvent("auth_state_callback_stale", "skipped", { generation, current: generationRef.current });
              return;
            }

            if (firebaseUser) {
              localStorage.setItem("cinequeue_local_owner", firebaseUser.uid);
              setLocalOwnerId(firebaseUser.uid);
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
                  authLog.debug("stale generation after getIdToken");
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
                setAuthToken(token);
                try {
                  localStorage.setItem("cinequeue_cached_user", JSON.stringify(uInfo));
                } catch {}
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
                    // Reuse a valid backend session; recent auth_time is required only for a new cookie.
                    let existingSession: UserMe | null = null;
                    let restoringSession = false;
                    try {
                      const encoded = token.split(".")[1];
                      if (encoded) {
                        const claims = JSON.parse(atob(encoded.replace(/-/g, "+").replace(/_/g, "/")));
                        restoringSession = typeof claims.auth_time === "number" &&
                          Date.now() / 1000 - claims.auth_time > 300;
                      }
                    } catch (err) {
                      authLog.debug("Session restoration hint unavailable", { error: (err as Error).message });
                    }
                    if (restoringSession) {
                      try {
                        existingSession = await api.me();
                      } catch (err) {
                        authLog.info("Existing session unavailable", { error: (err as Error).message });
                      }
                    }
                    if (!isCurrent()) return;
                    if (existingSession?.uid !== uInfo.uid) {
                      authLog.info("performAuthSequence: requesting CSRF token…");
                      recordEvent("csrf_request_started", "start");
                      const csrfData = await api.csrf();
                      authLog.info("performAuthSequence: CSRF token received");
                      recordEvent("csrf_request_completed", "success");
                      if (!isCurrent()) { authLog.debug("stale after CSRF"); return; }

                      authLog.info("performAuthSequence: calling createSession…");
                      recordEvent("session_creation_started", "start");
                      await api.createSession(token, csrfData.csrf_token);
                      authLog.info("performAuthSequence: createSession succeeded");
                      recordEvent("session_creation_completed", "success");
                      if (!isCurrent()) { authLog.debug("stale after createSession"); return; }
                    }

                    authLog.info("performAuthSequence: setting sessionReady=true, loading=false");
                    syncService.setAuthenticatedOwner(uInfo.uid);
                    setSessionReady(true);
                    setUser(uInfo);
                    setLoading(false);
                    setError(null);
                    recordEvent("auth_loading_cleared", "success");

                    // Set profile immediately from Firebase user data — no need to wait
                    // for /api/auth/me which uses the session cookie and may hit clock-skew sleep.
                    authLog.info("performAuthSequence: setting profile from Firebase data (non-blocking)");
                    setProfile({
                      uid: existingSession?.uid ?? uInfo.uid,
                      email: existingSession?.email ?? uInfo.email,
                      display_name: existingSession?.display_name ?? uInfo.display_name ?? null,
                      photo_url: existingSession?.photo_url ?? uInfo.photo_url ?? null
                    });
                    setProfileLoading(false);

                    // Start admin role check (uses Bearer token, not session cookie — fast)
                    authLog.info("performAuthSequence: starting adminMe role check");
                    const rolePromise = fetchAdminMe(token)
                      .then((res) => {
                        if (res && (res.is_admin === false || !res.username)) {
                          authLog.info("adminMe resolved: standard user (isAdmin=false)");
                          recordEvent("admin_me_request_completed", "success", { isAdmin: false });
                          if (!isCurrent()) return { isAdmin: false, role: "user", error: null };
                          setIsAdmin(false);
                          setRole("user");
                          setRoleLoading(false);
                          return { isAdmin: false, role: "user", error: null };
                        }
                        authLog.info("adminMe resolved: isAdmin=true");
                        recordEvent("admin_me_request_completed", "success");
                        if (!isCurrent()) return { isAdmin: true, role: "admin", error: null };
                        setIsAdmin(true);
                        setRole("admin");
                        setRoleLoading(false);
                        return { isAdmin: true, role: "admin", error: null };
                      })
                      .catch((err: any) => {
                        const isForbidden =
                          err.status === 403 ||
                          err.message?.includes("403") ||
                          err.message?.toLowerCase().includes("not authorized") ||
                          err.message?.toLowerCase().includes("forbidden");
                        if (isForbidden) {
                          authLog.info("adminMe resolved: standard user (isAdmin=false)");
                        } else {
                          authLog.warn("adminMe failed", { error: err.message, status: err.status });
                        }
                        recordEvent("admin_me_request_failed", "failure", { error: err.message });
                        if (!isCurrent()) return { isAdmin: false, role: null, error: err.message };
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
                    // Skip if existingSession already verified the session cookie at the start of performAuthSequence.
                    if (existingSession?.uid !== uInfo.uid) {
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
                    }

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
                    
                    // A cloud failure must not sign out the device workspace.
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
                setError(errMsg);
                recordEvent("auth_trace_completed", "success");
              }
            } else {
              authLog.info("onIdTokenChanged: NO user (signed out or first load with no session)");
              recordEvent("auth_state_no_user", "success");
              if (!isCurrent()) return;

              recordEvent("auth_context_state_update_started", "start");
              setAuthToken(null);
              try {
                localStorage.removeItem("cinequeue_cached_user");
              } catch {}
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
    const ownerId = sessionReady && user?.uid === localOwnerId ? user.uid : null;
    syncService.setAuthenticatedOwner(ownerId);
    if (ownerId) void syncService.triggerSync(ownerId);
    return () => syncService.setAuthenticatedOwner(null);
  }, [user, sessionReady, localOwnerId]);

  useEffect(() => {
    const handleUnauthorized = () => {
      syncService.setAuthenticatedOwner(null);
      setSessionReady(false);
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
    localStorage.removeItem("cinequeue_device_only");
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
    authSequenceRef.current++;
    setAuthToken(null);
    syncService.setAuthenticatedOwner(null);
    localStorage.removeItem("cinequeue_local_owner");
    localStorage.removeItem("cinequeue_cached_user");
    localStorage.setItem("cinequeue_device_only", "true");
    setLocalOwnerId("guest_local");
    setUser(null);
    setSessionReady(false);
    setIsAdmin(false);
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
    const generation = generationRef.current;
    const sequence = authSequenceRef.current;
    const isCurrent = () => generation === generationRef.current &&
      sequence === authSequenceRef.current &&
      localStorage.getItem("cinequeue_device_only") !== "true";
    const auth = await getFirebaseAuth();
    if (!isCurrent()) return;
    const currentUser = auth.currentUser;
    if (currentUser && currentUser.uid === localOwnerId) {
      setLoading(true);
      try {
        const token = await currentUser.getIdToken(true);
        if (!isCurrent()) return;
        const csrfData = await api.csrf();
        if (!isCurrent()) return;
        await api.createSession(token, csrfData.csrf_token);
        if (!isCurrent()) return;
        setSessionReady(true);
        const adminRes = await fetchAdminMe(token);
        if (!isCurrent()) return;
        setIsAdmin(Boolean(adminRes?.username && adminRes?.is_admin !== false));
      } catch (err: any) {
        if (!isCurrent()) return;
        setSessionReady(false);
        setIsAdmin(false);
        const isForbidden = err.message?.includes("403") || err.status === 403;
        if (!isForbidden) {
          setError(err.message || "Failed to refresh admin verification");
        }
      } finally {
        if (isCurrent()) setLoading(false);
      }
    }
  };

  const clearError = () => setError(null);
  const useDeviceWorkspace = () => {
    void logout();
  };

  return (
    <AuthContext.Provider value={{
      localOwnerId,
      useDeviceWorkspace,
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
  setAuthToken(null);
}
