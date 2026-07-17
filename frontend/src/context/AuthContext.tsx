import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  signOut as firebaseSignOut,
  Auth as FirebaseAuth
} from "firebase/auth";
import { api } from "../api";
import {
  startTrace,
  recordEvent,
  incrementCount,
} from "../utils/authPerformanceMonitor";

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
let authInitPromise: Promise<{ user: UserInfo | null; error: string | null }> | null = null;

async function getFirebaseAuth(): Promise<FirebaseAuth> {
  if (firebaseAuthInstance) {
    recordEvent("firebase_app_reused", "success");
    recordEvent("firebase_auth_instance_ready", "success");
    return firebaseAuthInstance;
  }

  if (firebaseAuthPromise) {
    return firebaseAuthPromise;
  }

  firebaseAuthPromise = (async () => {
    incrementCount("configFetches");
    recordEvent("firebase_config_fetch_started", "start");
    const config = await api.firebaseConfig();
    recordEvent("firebase_config_fetch_completed", "success");
    
    if (!config || !config.apiKey) {
      throw new Error("Firebase API key is missing or empty. Please verify your backend .env file contains FIREBASE_API_KEY and restart the backend server.");
    }
    
    let app;
    incrementCount("initAttempts");
    recordEvent("firebase_initialization_started", "start");
    if (getApps().length === 0) {
      app = initializeApp(config);
      recordEvent("firebase_app_created", "success");
    } else {
      app = getApp();
      recordEvent("firebase_app_reused", "success");
    }
    recordEvent("firebase_initialization_completed", "success");
    
    firebaseAuthInstance = getAuth(app);
    recordEvent("firebase_auth_instance_ready", "success");
    return firebaseAuthInstance;
  })();

  try {
    return await firebaseAuthPromise;
  } catch (err) {
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

    const initializeAuth = async () => {
      recordEvent("auth_context_state_update_started", "start");
      setLoading(true);
      setError(null);
      recordEvent("auth_context_state_update_completed", "success");

      try {
        const auth = await getFirebaseAuth();
        if (!isCurrent()) {
          recordEvent("auth_generation_stale", "skipped", { generation, current: generationRef.current });
          return;
        }

        if (!unsubscribeRef.current) {
          incrementCount("listenersRegistered");
          
          const unsubscribe = auth.onIdTokenChanged(async (firebaseUser) => {
            recordEvent("auth_state_callback_started", "start");
            incrementCount("callbacks");

            if (!isCurrent()) {
              recordEvent("auth_state_callback_stale", "skipped", { generation, current: generationRef.current });
              return;
            }

            if (firebaseUser) {
              recordEvent("auth_state_user_available", "success", { uid: firebaseUser.uid, email: firebaseUser.email });
              
              try {
                incrementCount("getIdTokenCalls");
                recordEvent("id_token_request_started", "start");
                const token = await firebaseUser.getIdToken();
                recordEvent("id_token_request_completed", "success");

                if (!isCurrent()) return;

                const uInfo: UserInfo = {
                  uid: firebaseUser.uid,
                  email: firebaseUser.email ?? "",
                  display_name: firebaseUser.displayName ?? null,
                  photo_url: firebaseUser.photoURL ?? null
                };

                // Fast Auth Resolution: set core state immediately and clear global loading!
                recordEvent("auth_context_state_update_started", "start");
                setFirebaseUser(uInfo);
                setIdToken(token);
                setAuthReady(true);
                setUser(uInfo);
                setAuthInitialized(true);
                setLoading(false);
                setSessionReady(false);
                setRoleLoading(true);
                setProfileLoading(true);
                setAuthorizationReady(false);
                setError(null);
                recordEvent("auth_context_state_update_completed", "success");
                recordEvent("auth_loading_cleared", "success");

                const performAuthSequence = async () => {
                  try {
                    recordEvent("csrf_request_started", "start");
                    const csrfData = await api.csrf();
                    recordEvent("csrf_request_completed", "success");
                    if (!isCurrent()) return;

                    recordEvent("session_creation_started", "start");
                    await api.createSession(token, csrfData.csrf_token);
                    recordEvent("session_creation_completed", "success");
                    if (!isCurrent()) return;

                    setSessionReady(true);

                    // Start secondary async requests concurrently (role lookup & session/profile verification)
                    const rolePromise = fetchAdminMe(token)
                      .then(() => {
                        recordEvent("admin_me_request_completed", "success");
                        if (!isCurrent()) return { isAdmin: true, role: "admin", error: null };
                        setIsAdmin(true);
                        setRole("admin");
                        setRoleLoading(false);
                        return { isAdmin: true, role: "admin", error: null };
                      })
                      .catch((err: any) => {
                        recordEvent("admin_me_request_failed", "failure", { error: err.message });
                        if (!isCurrent()) return { isAdmin: false, role: null, error: err.message };
                        const isForbidden = err.message?.includes("403") || err.status === 403;
                        setIsAdmin(false);
                        setRole(isForbidden ? "user" : null);
                        setRoleLoading(false);
                        return {
                          isAdmin: false,
                          role: isForbidden ? "user" : null,
                          error: isForbidden ? null : (err.message || "Failed to resolve admin verification")
                        };
                      });

                    const profilePromise = (async () => {
                      try {
                        recordEvent("profile_request_started", "start");
                        const pData = await api.me();
                        recordEvent("profile_request_completed", "success");
                        if (!isCurrent()) return;

                        setProfile({
                          uid: pData.uid,
                          email: pData.email,
                          display_name: pData.display_name ?? null,
                          photo_url: pData.photo_url ?? null
                        });
                      } catch (profileErr: any) {
                        recordEvent("profile_request_failed", "failure", { error: profileErr.message });
                      } finally {
                        setProfileLoading(false);
                      }
                    })();

                    const [roleResult] = await Promise.all([rolePromise, profilePromise]);
                    if (!isCurrent()) return;

                    recordEvent("auth_context_state_update_started", "start");
                    if (roleResult.error) {
                      setError(roleResult.error);
                    }
                    recordEvent("authorization_ready", "success");
                    setAuthorizationReady(true);
                    recordEvent("auth_context_state_update_completed", "success");
                    recordEvent("auth_state_callback_completed", "success");
                    recordEvent("auth_trace_completed", "success");

                  } catch (err: any) {
                    if (!isCurrent()) return;
                    
                    recordEvent("auth_context_state_update_started", "start");
                    setError(err.message || "Session or role resolution failed");
                    setSessionReady(false);
                    setIsAdmin(false);
                    setRole(null);
                    setRoleLoading(false);
                    setProfileLoading(false);
                    recordEvent("authorization_ready", "failure");
                    setAuthorizationReady(true);
                    recordEvent("auth_context_state_update_completed", "success");
                    recordEvent("auth_state_callback_completed", "success");
                    recordEvent("auth_trace_completed", "success");
                  }
                };

                void performAuthSequence();

              } catch (err: any) {
                if (!isCurrent()) return;
                recordEvent("auth_context_state_update_started", "start");
                setError(err.message || "Failed to resolve authentication");
                setAuthInitialized(true);
                setLoading(false);
                setAuthorizationReady(true);
                recordEvent("auth_context_state_update_completed", "success");
                recordEvent("auth_state_callback_completed", "success");
                recordEvent("auth_trace_completed", "success");
              }
            } else {
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
              setError(null);
              setAuthInitialized(true);
              setLoading(false);
              recordEvent("auth_context_state_update_completed", "success");
              recordEvent("auth_state_callback_completed", "success");
              recordEvent("auth_loading_cleared", "success");
              recordEvent("auth_trace_completed", "success");
            }
          });

          unsubscribeRef.current = unsubscribe;
          recordEvent("auth_state_listener_registered", "success");
        }

        const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
        
        if (isLocal) {
          // No-op: the onIdTokenChanged observer will fire immediately and handle it.
        } else {
          if (!authInitPromise) {
            authInitPromise = (async () => {
              let errorMsg: string | null = null;
              try {
                recordEvent("id_token_request_started", "start", { source: "getRedirectResult" });
                const userCredential = await getRedirectResult(auth);
                recordEvent("id_token_request_completed", "success");

                if (userCredential) {
                  incrementCount("getIdTokenCalls");
                  recordEvent("id_token_request_started", "start");
                  const idToken = await userCredential.user.getIdToken();
                  recordEvent("id_token_request_completed", "success");
                  
                  const csrfData = await api.csrf();
                  await api.createSession(idToken, csrfData.csrf_token);
                  await firebaseSignOut(auth);
                }
              } catch (err: any) {
                console.error("Redirect authentication failed:", err);
                errorMsg = "Google Sign-In failed. Please try again.";
              }

              let loggedInUser: UserInfo | null = null;
              try {
                const data = await api.me();
                loggedInUser = {
                  uid: data.uid,
                  email: data.email,
                  display_name: data.display_name ?? null,
                  photo_url: data.photo_url ?? null
                };
              } catch (err) {
                loggedInUser = null;
              }

              return { user: loggedInUser, error: errorMsg };
            })();
          }

          const result = await authInitPromise;
          if (!isCurrent()) return;

          recordEvent("auth_context_state_update_started", "start");
          setUser(result.user);
          setFirebaseUser(result.user);
          setError(result.error);
          setAuthInitialized(true);
          setLoading(false);
          setAuthReady(true);
          setAuthorizationReady(true);
          recordEvent("auth_context_state_update_completed", "success");
        }

      } catch (err: any) {
        if (!isCurrent()) return;
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
    };
    window.addEventListener("cinequeue-unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("cinequeue-unauthorized", handleUnauthorized);
    };
  }, []);

  const loginWithGoogle = async () => {
    startTrace();
    recordEvent("auth_context_state_update_started", "start");
    setError(null);
    setLoading(true);
    recordEvent("auth_context_state_update_completed", "success");
    
    const coopReferrer = document.referrer || "unknown";

    try {
      const auth = await getFirebaseAuth();
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      
      const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
      if (isLocal) {
        incrementCount("popupLogins");
        recordEvent("popup_login_started", "start");
        const userCredential = await signInWithPopup(auth, provider);
        recordEvent("popup_login_completed", "success", { uid: userCredential.user.uid });
      } else {
        recordEvent("popup_login_started", "start", { method: "redirect" });
        await signInWithRedirect(auth, provider);
      }
    } catch (err: any) {
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
  authInitPromise = null;
}
