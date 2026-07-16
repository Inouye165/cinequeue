import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AdminDashboard } from "./pages/AdminDashboard";
import { AdminLogin } from "./pages/AdminLogin";
import { UserLogin } from "./pages/UserLogin";
import { CinequeueDashboard } from "./pages/CinequeueDashboard";

function CinequeueApp() {
  const { user, loading: authLoading, error: authError, loginWithGoogle } = useAuth();

  // Admin Portal state variables
  const [adminUsername, setAdminUsername] = useState<string | null>(null);
  const [showAdminLogin, setShowAdminLogin] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);
  const [adminLoading, setAdminLoading] = useState(false);

  // Admin Dashboard data variables
  const [approvals, setApprovals] = useState<any[]>([]);
  const [loginLogs, setLoginLogs] = useState<any[]>([]);

  const loadAdminData = useCallback(async () => {
    try {
      const reqs = await api.adminRequests();
      setApprovals(reqs.approvals);
      const logs = await api.adminLoginLogs();
      setLoginLogs(logs.logs);
    } catch (err) {
      console.error("Failed to load admin data:", err);
    }
  }, []);

  // Restore Admin session if active on mount
  useEffect(() => {
    const checkAdmin = async () => {
      try {
        const data = await api.adminMe();
        setAdminUsername(data.username);
      } catch (err) {
        // No active admin session
      }
    };
    void checkAdmin();
  }, []);

  useEffect(() => {
    if (adminUsername) {
      void loadAdminData();
    }
  }, [adminUsername, loadAdminData]);

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
    } catch (err) {
      console.error("Logout failed:", err);
    } finally {
      setAdminUsername(null);
    }
  };

  const handleApprove = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminApprove(email, csrfRes.csrf_token);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to approve user.");
    }
  };

  const handleDeny = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminDeny(email, csrfRes.csrf_token);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to revoke/deny user.");
    }
  };

  const handleInvite = async (email: string) => {
    try {
      const csrfRes = await api.csrf();
      await api.adminInvite(email, csrfRes.csrf_token);
      await loadAdminData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to invite user.");
      throw err;
    }
  };

  if (authLoading) {
    return (
      <div className="auth-loading">
        <div className="spinner"></div>
        <p>Verifying session…</p>
      </div>
    );
  }

  // 1. Render Admin Dashboard if Admin is logged in
  if (adminUsername) {
    return (
      <AdminDashboard
        adminUsername={adminUsername}
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
    </AuthProvider>
  );
}
