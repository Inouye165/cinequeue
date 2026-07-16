import React, { createContext, useContext, useEffect, useState } from "react";
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

export interface UserInfo {
  uid: string;
  email: string;
  display_name: string | null;
  photo_url: string | null;
}

interface AuthContextType {
  user: UserInfo | null;
  loading: boolean;
  error: string | null;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

let firebaseAuthInstance: FirebaseAuth | null = null;
let authInitPromise: Promise<{ user: UserInfo | null; error: string | null }> | null = null;

async function getFirebaseAuth(): Promise<FirebaseAuth> {
  if (firebaseAuthInstance) return firebaseAuthInstance;

  const config = await api.firebaseConfig();
  console.log("Firebase Config fetched:", config);
  
  if (!config || !config.apiKey) {
    throw new Error("Firebase API key is missing or empty. Please verify your backend .env file contains FIREBASE_API_KEY and restart the backend server.");
  }
  
  let app;
  if (getApps().length === 0) {
    app = initializeApp(config);
    console.log("Initialized new Firebase App");
  } else {
    app = getApp();
    console.log("Re-using existing Firebase App");
  }
  
  firebaseAuthInstance = getAuth(app);
  console.log("Firebase Auth instance:", firebaseAuthInstance);
  return firebaseAuthInstance;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);



  useEffect(() => {
    const initializeAuth = async () => {
      setLoading(true);
      setError(null);
      try {
        const auth = await getFirebaseAuth();
        const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
        
        if (isLocal) {
          // Local development: bypass redirect check because HTTP/HTTPS third-party cookie restrictions block it
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
          setUser(loggedInUser);
        } else {
          // Production/Mobile: Resolve redirect result
          if (!authInitPromise) {
            authInitPromise = (async () => {
              let errorMsg: string | null = null;
              try {
                const userCredential = await getRedirectResult(auth);
                if (userCredential) {
                  console.log("Redirect result found, user credential exists");
                  const idToken = await userCredential.user.getIdToken();
                  
                  const csrfData = await api.csrf();
                  const csrfToken = csrfData.csrf_token;
                  
                  await api.createSession(idToken, csrfToken);
                  await firebaseSignOut(auth);
                }
              } catch (err: any) {
                console.error("Redirect auth action failed:", err);
                errorMsg = "Google Sign-In failed. Please try again.";
                if (err.code === "auth/account-exists-with-different-credential") {
                  errorMsg = "An account already exists with a different credential.";
                } else if (err.code === "auth/credential-already-in-use") {
                  errorMsg = "This credential is already in use by another account.";
                } else if (err.message && err.message.includes("403")) {
                  errorMsg = "Your Google account is not authorized to access Cinequeue.";
                } else if (err instanceof Error) {
                  errorMsg = err.message;
                }
              }

              // Fetch current user from backend session
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
          setUser(result.user);
          setError(result.error);
        }
      } catch (err: any) {
        console.error("Initialization wrapper failed:", err);
        setError(err.message || "Initialization failed");
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    void initializeAuth();
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
    };
    window.addEventListener("cinequeue-unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("cinequeue-unauthorized", handleUnauthorized);
    };
  }, []);

  const loginWithGoogle = async () => {
    setError(null);
    setLoading(true);
    try {
      const auth = await getFirebaseAuth();
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: "select_account" });
      
      const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
      if (isLocal) {
        // Use popup locally to avoid cross-origin redirection blocks over HTTP
        const userCredential = await signInWithPopup(auth, provider);
        const idToken = await userCredential.user.getIdToken();
        
        const csrfData = await api.csrf();
        const csrfToken = csrfData.csrf_token;
        
        await api.createSession(idToken, csrfToken);
        await firebaseSignOut(auth);
        
        const data = await api.me();
        setUser({
          uid: data.uid,
          email: data.email,
          display_name: data.display_name ?? null,
          photo_url: data.photo_url ?? null
        });
        setLoading(false);
      } else {
        // Use redirect in production/mobile to avoid COOP warnings
        await signInWithRedirect(auth, provider);
      }
    } catch (err: any) {
      console.error("Auth action failed:", err);
      let msg = "Google Sign-In failed. Please try again.";
      if (err.code === "auth/popup-blocked") {
        msg = "Sign-in popup was blocked by your browser. Please enable popups for this site.";
      } else if (err.code === "auth/popup-closed-by-user") {
        msg = "Sign-in popup was closed before completion.";
      } else if (err.message && err.message.includes("403")) {
        msg = "Your Google account is not authorized to access Cinequeue.";
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setError(msg);
      setUser(null);
      setLoading(false);
    }
  };

  const logout = async () => {
    setError(null);
    setLoading(true);
    try {
      const csrfData = await api.csrf();
      await api.logout(csrfData.csrf_token);
    } catch (err) {
      console.error("Auth action failed:", err);
    } finally {
      setUser(null);
      setLoading(false);
    }
  };

  const clearError = () => setError(null);

  return (
    <AuthContext.Provider value={{ user, loading, error, loginWithGoogle, logout, clearError }}>
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
