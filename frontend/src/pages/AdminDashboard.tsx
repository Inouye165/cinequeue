import { FormEvent, useState } from "react";

interface AdminDashboardProps {
  adminUsername: string;
  approvals: any[];
  loginLogs: any[];
  onLogout: () => void;
  onApprove: (email: string) => void;
  onDeny: (email: string) => void;
  onInvite: (email: string) => Promise<void>;
}

export function AdminDashboard({
  adminUsername,
  approvals,
  loginLogs,
  onLogout,
  onApprove,
  onDeny,
  onInvite,
}: AdminDashboardProps) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [adminTab, setAdminTab] = useState<"requests" | "users" | "logs">("requests");

  const handleInviteSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    void onInvite(inviteEmail.trim()).then(() => {
      setInviteEmail("");
    });
  };

  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const otherUsers = approvals.filter((a) => a.status !== "pending");

  return (
    <div className="admin-dashboard-container">
      <div className="admin-header-bar">
        <div>
          <h1>Cinequeue Admin Panel</h1>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>
            Logged in as <strong>{adminUsername}</strong>
          </p>
        </div>
        <button className="logout-btn" onClick={onLogout}>Sign Out Admin</button>
      </div>

      <div className="admin-tabs">
        <button
          className={`admin-tab ${adminTab === "requests" ? "active" : ""}`}
          onClick={() => setAdminTab("requests")}
        >
          Pending Requests ({pendingApprovals.length})
        </button>
        <button
          className={`admin-tab ${adminTab === "users" ? "active" : ""}`}
          onClick={() => setAdminTab("users")}
        >
          Manage Users ({otherUsers.length})
        </button>
        <button
          className={`admin-tab ${adminTab === "logs" ? "active" : ""}`}
          onClick={() => setAdminTab("logs")}
        >
          Security Audit Logs ({loginLogs.length})
        </button>
      </div>

      {adminTab === "requests" && (
        <div className="admin-card">
          <h2>Access Requests awaiting approval</h2>
          {pendingApprovals.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>No pending access requests.</p>
          ) : (
            <div className="admin-table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Email Address</th>
                    <th>Requested At</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingApprovals.map((req) => (
                    <tr key={req.email}>
                      <td><strong>{req.email}</strong></td>
                      <td>{new Date(req.requested_at).toLocaleString()}</td>
                      <td className="admin-actions-cell">
                        <button
                          className="admin-btn admin-btn-success"
                          onClick={() => onApprove(req.email)}
                        >
                          Approve
                        </button>
                        <button
                          className="admin-btn admin-btn-danger"
                          onClick={() => onDeny(req.email)}
                        >
                          Deny
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {adminTab === "users" && (
        <>
          <div className="admin-card">
            <h2>Send an Invite / Pre-approve Email</h2>
            <form onSubmit={handleInviteSubmit} className="admin-invite-form">
              <input
                type="email"
                className="admin-input"
                placeholder="user@example.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
              />
              <button type="submit" className="admin-btn admin-btn-primary">Send Invite</button>
            </form>
          </div>

          <div className="admin-card">
            <h2>All Approved and Revoked Users</h2>
            {otherUsers.length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>No other users registered.</p>
            ) : (
              <div className="admin-table-container">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Email Address</th>
                      <th>Status</th>
                      <th>Decided By</th>
                      <th>Decided At</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {otherUsers.map((item) => (
                      <tr key={item.email}>
                        <td><strong>{item.email}</strong></td>
                        <td>
                          <span className={`badge-status ${item.status}`}>
                            {item.status}
                          </span>
                        </td>
                        <td>{item.decided_by || "-"}</td>
                        <td>{item.decided_at ? new Date(item.decided_at).toLocaleString() : "-"}</td>
                        <td className="admin-actions-cell">
                          {item.status === "approved" ? (
                            <button
                              className="admin-btn admin-btn-danger"
                              onClick={() => onDeny(item.email)}
                            >
                              Revoke Access
                            </button>
                          ) : (
                            <button
                              className="admin-btn admin-btn-success"
                              onClick={() => onApprove(item.email)}
                            >
                              Re-approve
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {adminTab === "logs" && (
        <div className="admin-card">
          <h2>Security Audit Logs</h2>
          {loginLogs.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>No login logs available.</p>
          ) : (
            <div className="admin-table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>User / Email</th>
                    <th>Time</th>
                    <th>Result</th>
                    <th>Reason</th>
                    <th>IP Address</th>
                    <th>User Agent</th>
                  </tr>
                </thead>
                <tbody>
                  {loginLogs.map((log) => (
                    <tr key={log.id}>
                      <td><strong>{log.email}</strong></td>
                      <td>{new Date(log.timestamp).toLocaleString()}</td>
                      <td>
                        <span className={`badge-status ${log.status === "success" ? "success-log" : "failed-log"}`}>
                          {log.status}
                        </span>
                      </td>
                      <td><code>{log.reason}</code></td>
                      <td>{log.ip_address || "unknown"}</td>
                      <td>
                        <span className="admin-meta-info" title={log.user_agent}>
                          {log.user_agent ? (log.user_agent.length > 40 ? log.user_agent.substring(0, 40) + "..." : log.user_agent) : "unknown"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
