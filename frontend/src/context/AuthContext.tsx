import React, { createContext, useContext, useEffect, useState } from "react";
import { initializeApp, getApps, getApp, deleteApp } from "firebase/app";
import {
  initializeAuth,
  inMemoryPersistence,
  GoogleAuthProvider,
  signInWithPopup,
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

async function getFirebaseAuth(): Promise<FirebaseAuth> {
  if (firebaseAuthInstance) return firebaseAuthInstance;

  const config = await api.firebaseConfig();
  let app;
  if (getApps().length === 0) {
    app = initializeApp(config);
  } else {
    app = getApp();
    try {
      await deleteApp(app);
    } catch (err) {
      console.warn("Failed to delete existing app:", err);
    }
    app = initializeApp(config);
  }
  firebaseAuthInstance = initializeAuth(app, {
    persistence: inMemoryPersistence
  });
  return firebaseAuthInstance;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMe = async () => {
    try {
      const data = await api.me();
      setUser({
        uid: data.uid,
        email: data.email,
        display_name: data.display_name ?? null,
        photo_url: data.photo_url ?? null
      });
    } catch (err) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchMe();
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
      
      const userCredential = await signInWithPopup(auth, provider);
      const idToken = await userCredential.user.getIdToken();
      
      const csrfData = await api.csrf();
      const csrfToken = csrfData.csrf_token;
      
      await api.createSession(idToken, csrfToken);
      await firebaseSignOut(auth);
      await fetchMe();
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
