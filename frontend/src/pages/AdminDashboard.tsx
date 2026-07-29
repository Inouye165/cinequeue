import { FormEvent, useState } from "react";
import { AiAgentDecisionsTab } from "../components/admin/AiAgentDecisionsTab";

interface AdminDashboardProps {
  adminUsername: string;
  approvals: any[];
  loginLogs: any[];
  authToken?: string;
  onLogout: () => void;
  onApprove: (email: string) => void;
  onDeny: (email: string) => void;
  onInvite: (email: string) => Promise<{ status?: string; email?: string; email_sent?: boolean; message?: string } | void>;
}

export function AdminDashboard({
  adminUsername,
  approvals,
  loginLogs,
  authToken,
  onLogout,
  onApprove,
  onDeny,
  onInvite,
}: AdminDashboardProps) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [adminTab, setAdminTab] = useState<"requests" | "users" | "logs" | "decisions">("requests");
  const [isSubmittingInvite, setIsSubmittingInvite] = useState(false);
  const [inviteFeedback, setInviteFeedback] = useState<{
    type: "success" | "warning" | "error";
    message: string;
    email: string;
    emailSent?: boolean;
  } | null>(null);
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null);
  const [logSearchEmail, setLogSearchEmail] = useState("");
  const [logFilterStatus, setLogFilterStatus] = useState<string>("all");
  const [logFilterReason, setLogFilterReason] = useState<string>("all");

  const formatAuditReason = (reason: string): string => {
    switch (reason) {
      case "google_login":
        return "Google Sign-In";
      case "session_restoration":
        return "Session Restored";
      case "admin_login":
        return "Admin Login";
      case "pending_approval":
        return "Pending Approval";
      case "revoked_user":
        return "Access Revoked";
      case "csrf_validation_failed":
        return "CSRF Failure";
      case "origin_validation_failed":
        return "Origin Failure";
      case "invalid_id_token":
        return "Invalid Token";
      case "auth_time_expired":
        return "Token Expired";
      case "email_not_verified":
        return "Unverified Email";
      case "invite_email_dispatched":
      case "invite_preapproved_no_email":
        return "Invited / Pre-approved";
      default:
        return reason ? reason.replace(/_/g, " ") : "Unknown";
    }
  };

  const filteredLogs = loginLogs.filter((log) => {
    if (logSearchEmail) {
      const target = logSearchEmail.trim().toLowerCase();
      if (!log.email.toLowerCase().includes(target)) return false;
    }
    if (logFilterStatus !== "all") {
      if (log.status !== logFilterStatus) return false;
    }
    if (logFilterReason !== "all") {
      if (log.reason !== logFilterReason) return false;
    }
    return true;
  });

  const copyInviteInstructions = (email: string) => {
    const inviteUrl = window.location.origin;
    const text = `Hey! I've pre-approved your email (${email}) for CineQueue. You can sign in here: ${inviteUrl}`;
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedEmail(email);
      setTimeout(() => setCopiedEmail(null), 3000);
    });
  };

  const handleInviteSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const targetEmail = inviteEmail.trim();
    if (!targetEmail) return;

    setIsSubmittingInvite(true);
    setInviteFeedback(null);

    try {
      const res = await onInvite(targetEmail);
      const emailSent = res?.email_sent ?? false;
      const msg = res?.message || (emailSent ? `Invitation email sent to ${targetEmail}` : `Pre-approved ${targetEmail}`);

      setInviteFeedback({
        type: emailSent ? "success" : "warning",
        message: msg,
        email: targetEmail,
        emailSent,
      });
      setInviteEmail("");
    } catch (err) {
      setInviteFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to send invite.",
        email: targetEmail,
      });
    } finally {
      setIsSubmittingInvite(false);
    }
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
          Authentication Activity ({loginLogs.length})
        </button>
        <button
          className={`admin-tab ${adminTab === "decisions" ? "active" : ""}`}
          onClick={() => setAdminTab("decisions")}
        >
          🤖 AI Agent Decisions
        </button>
      </div>

      {adminTab === "decisions" && (
        <AiAgentDecisionsTab authToken={authToken} />
      )}


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
                disabled={isSubmittingInvite}
              />
              <button
                type="submit"
                className="admin-btn admin-btn-primary"
                disabled={isSubmittingInvite}
              >
                {isSubmittingInvite ? "Inviting…" : "Send Invite"}
              </button>
            </form>

            {inviteFeedback && (
              <div className={`admin-feedback-banner ${inviteFeedback.type}`}>
                <div>
                  <strong>
                    {inviteFeedback.type === "success" && "✅ Invite Dispatched"}
                    {inviteFeedback.type === "warning" && "ℹ️ User Pre-approved (SMTP Email Delivery Unconfigured)"}
                    {inviteFeedback.type === "error" && "❌ Invite Failed"}
                  </strong>
                  <p style={{ margin: "4px 0 0" }}>{inviteFeedback.message}</p>
                </div>
                <div className="admin-feedback-actions">
                  <button
                    type="button"
                    className="copy-btn"
                    onClick={() => copyInviteInstructions(inviteFeedback.email)}
                  >
                    {copiedEmail === inviteFeedback.email ? "✓ Copied Link & Text!" : "📋 Copy Invite Link & Text"}
                  </button>
                </div>
              </div>
            )}
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
                            <>
                              <button
                                type="button"
                                className="copy-btn"
                                style={{ padding: "4px 10px", fontSize: "0.8rem" }}
                                onClick={() => copyInviteInstructions(item.email)}
                              >
                                {copiedEmail === item.email ? "✓ Copied!" : "📋 Copy Link"}
                              </button>
                              <button
                                className="admin-btn admin-btn-danger"
                                onClick={() => onDeny(item.email)}
                              >
                                Revoke Access
                              </button>
                            </>
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
          <h2>Authentication Activity</h2>
          <div style={{ display: "flex", gap: "12px", marginBottom: "16px", alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="text"
              className="admin-input"
              style={{ maxWidth: "260px" }}
              placeholder="Search by email..."
              value={logSearchEmail}
              onChange={(e) => setLogSearchEmail(e.target.value)}
            />
            <select
              className="admin-input"
              style={{ maxWidth: "150px" }}
              value={logFilterStatus}
              onChange={(e) => setLogFilterStatus(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
            </select>
            <select
              className="admin-input"
              style={{ maxWidth: "200px" }}
              value={logFilterReason}
              onChange={(e) => setLogFilterReason(e.target.value)}
            >
              <option value="all">All Event Reasons</option>
              <option value="google_login">Google Sign-In</option>
              <option value="session_restoration">Session Restored</option>
              <option value="admin_login">Admin Login</option>
              <option value="pending_approval">Pending Approval</option>
              <option value="revoked_user">Access Revoked</option>
              <option value="csrf_validation_failed">CSRF Failure</option>
              <option value="origin_validation_failed">Origin Failure</option>
            </select>
          </div>
          {filteredLogs.length === 0 ? (
            <p style={{ color: "var(--text-muted)" }}>No matching authentication activity records available.</p>
          ) : (
            <div className="admin-table-container">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>User / Email</th>
                    <th>Time</th>
                    <th>Result</th>
                    <th>Event Reason</th>
                    <th>IP Address</th>
                    <th>User Agent</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLogs.map((log) => (
                    <tr key={log.id}>
                      <td><strong>{log.email}</strong></td>
                      <td>{new Date(log.timestamp).toLocaleString()}</td>
                      <td>
                        <span className={`badge-status ${log.status === "success" ? "success-log" : "failed-log"}`}>
                          {log.status}
                        </span>
                      </td>
                      <td>
                        <strong>{formatAuditReason(log.reason)}</strong>
                        <br />
                        <code style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{log.reason}</code>
                      </td>
                      <td>{log.ip_address || "unknown"}</td>
                      <td>
                        <span className="admin-meta-info" title={log.user_agent}>
                          {log.user_agent ? (log.user_agent.length > 35 ? log.user_agent.substring(0, 35) + "..." : log.user_agent) : "unknown"}
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
