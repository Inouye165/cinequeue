import { FormEvent, useState } from "react";

interface AdminLoginProps {
  onLogin: (username: string, password: string) => Promise<void>;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
}

export function AdminLogin({ onLogin, onCancel, loading, error }: AdminLoginProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    void onLogin(username.trim(), password.trim());
  };

  return (
    <div className="auth-container">
      <div className="auth-card" style={{ maxWidth: "420px" }}>
        <h1>Admin Portal</h1>
        <p>Login with your administrator credentials.</p>

        {error ? (
          <div style={{ marginBottom: "20px" }} className="error-banner">{error}</div>
        ) : null}

        <form onSubmit={handleSubmit}>
          <div className="admin-form-group">
            <label>Username</label>
            <input
              type="text"
              className="admin-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              required
            />
          </div>

          <div className="admin-form-group">
            <label>Password</label>
            <input
              type="password"
              className="admin-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            className="login-btn"
            style={{
              background: "var(--accent)",
              color: "#171b26",
              width: "100%",
              cursor: loading ? "wait" : "pointer"
            }}
            disabled={loading}
          >
            {loading ? "Verifying..." : "Sign In as Admin"}
          </button>
        </form>

        <span
          className="admin-login-toggle-link"
          onClick={onCancel}
        >
          Sign In with Google instead
        </span>
      </div>
    </div>
  );
}
