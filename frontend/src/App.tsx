import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AdminDashboard } from "./pages/AdminDashboard";
import { AdminLogin } from "./pages/AdminLogin";
import { UserLogin } from "./pages/UserLogin";
import { CinequeueDashboard } from "./pages/CinequeueDashboard";
import { AuthDiagnosticsPanel } from "./components/AuthDiagnosticsPanel";
import { recordEvent } from "./utils/authPerformanceMonitor";

function CinequeueApp() {
  const {
    user,
    isAdmin: contextIsAdmin,
    authInitialized,
    loading: authLoading,
    error: authError,
    loginWithGoogle,
    logout,
    authorizationReady,
    profile,
    sessionReady,
    idToken
  } = useAuth();

  // Admin Portal state variables (for traditional cookie login fallback)
  const [adminUsername, setAdminUsername] = useState<string | null>(null);
  const [showAdminLogin, setShowAdminLogin] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminLoading, setAdminLoading] = useState(false);

  // Admin Dashboard data variables
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loginLogs, setLoginLogs] = useState<any[]>([]);

  const activeAdminName = adminUsername || (contextIsAdmin && (profile?.email || user?.email) ? (profile?.email || user?.email) : null);

  const loadAdminData = useCallback(async (signal?: AbortSignal) => {
    recordEvent("admin_requests_started", "start");
    try {
      const reqs = await api.adminRequests(idToken || undefined, signal);
      if (signal?.aborted) return;
      setApprovals(reqs.approvals);
      const logs = await api.adminLoginLogs(idToken || undefined, signal);
      if (signal?.aborted) return;
      setLoginLogs(logs.logs);
      recordEvent("admin_requests_completed", "success");
    } catch (err: any) {
      if (err.name === "AbortError" || signal?.aborted) {
        return;
      }
      recordEvent("admin_requests_completed", "failure", { error: err.message });
      console.error("Failed to load admin data:", err);
    }
  }, [idToken]);

  useEffect(() => {
    const isGoogleAdmin = authInitialized && sessionReady && authorizationReady && contextIsAdmin;
    const isTraditionalAdmin = !!adminUsername;
    const hasAdminSession = isTraditionalAdmin || isGoogleAdmin;

    if (!hasAdminSession) {
      setApprovals([]);
      setLoginLogs([]);
      if (activeAdminName) {
        recordEvent("admin_requests_skipped", "skipped", {
          reason: "not_fully_authorized",
          authInitialized,
          sessionReady,
          authorizationReady,
          contextIsAdmin
        });
      }
      return;
    }

    const controller = new AbortController();
    void loadAdminData(controller.signal);

    return () => {
      controller.abort();
    };
  }, [adminUsername, authInitialized, sessionReady, authorizationReady, contextIsAdmin, activeAdminName, loadAdminData]);

  // Admin action handlers
  const handleAdminLogin = async (usernameInput: string, passwordInput: string) => {
    setAdminLoading(true);
    setAdminError(null);
    try {
      const csrfRes = await api.csrf();
      await api.adminLogin(usernameInput, passwordInput, csrfRes.csrf_token);
      setAdminUsername(usernameInput);
      setShowAdminLogin(false);
    } catch (err) {
      setAdminError(err instanceof Error ? err.message : "Admin login failed.");
    } finally {
      setAdminLoading(false);
    }
  };

  const handleAdminLogout = async () => {
    try {
      const csrfRes = await api.csrf();
      await api.adminLogout(csrfRes.csrf_token);
      await logout();
    } catch (err) {
      console.error("Logout failed:", err);
    } finally {
      setAdminUsername(null);
    }
  };

  const handleApprove = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminApprove(email, csrfRes.csrf_token, idToken || undefined);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to approve user.");
    }
  };

  const handleDeny = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminDeny(email, csrfRes.csrf_token, idToken || undefined);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to revoke/deny user.");
    }
  };

  const handleInvite = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminInvite(email, csrfRes.csrf_token, idToken || undefined);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to invite user.");
      throw err;
    }
  };

  if (!authInitialized || authLoading || (user && !authorizationReady)) {
    return (
      <div className="auth-loading">
        <div className="spinner"></div>
        <p>Verifying session…</p>
      </div>
    );
  }

  // 1. Render Admin Dashboard if Admin is logged in
  if (activeAdminName) {
    return (
      <AdminDashboard
        adminUsername={activeAdminName}
        approvals={approvals}
        loginLogs={loginLogs}
        onLogout={handleAdminLogout}
        onApprove={handleApprove}
        onDeny={handleDeny}
        onInvite={handleInvite}
      />
    );
  }

  // 2. Render Login Cards if Regular User is not logged in
  if (!user) {
    if (showAdminLogin) {
      return (
        <AdminLogin
          onLogin={handleAdminLogin}
          onCancel={() => {
            setShowAdminLogin(false);
            setAdminError(null);
          }}
          loading={adminLoading}
          error={adminError}
        />
      );
    }

    return (
      <UserLogin
        authError={authError}
        onLoginWithGoogle={loginWithGoogle}
        onAdminToggle={() => {
          setShowAdminLogin(true);
          setAdminError(null);
        }}
      />
    );
  }

  // 3. Render Main Cinequeue Watchlist App
  return <CinequeueDashboard />;
}

export default function App() {
  return (
    <AuthProvider>
      <CinequeueApp />
      <AuthDiagnosticsPanel />
    </AuthProvider>
  );
}
