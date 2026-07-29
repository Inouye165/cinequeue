import { useEffect, useState } from "react";
import { syncService, type SyncStatusInfo } from "../services/syncService";
import { movieService } from "../services/movieService";

interface SyncStatusBarProps {
  ownerId: string;
  onDataCleared?: () => void;
}

export function SyncStatusBar({ ownerId, onDataCleared }: SyncStatusBarProps) {
  const [status, setStatus] = useState<SyncStatusInfo>(syncService.getStatus());
  const [showClearModal, setShowClearModal] = useState(false);

  useEffect(() => {
    const unsubscribe = syncService.subscribe((newStatus) => {
      setStatus(newStatus);
    });
    return unsubscribe;
  }, []);

  const handleSyncClick = () => {
    void syncService.triggerSync(ownerId);
  };

  const handleClearConfirm = async () => {
    await movieService.clearLocalData(ownerId);
    setShowClearModal(false);
    if (onDataCleared) onDataCleared();
  };

  const getBadgeStyle = () => {
    switch (status.state) {
      case "synced":
        return { bg: "rgba(46, 204, 113, 0.15)", border: "#2ecc71", color: "#2ecc71", text: "Synced" };
      case "syncing":
        return { bg: "rgba(52, 152, 219, 0.15)", border: "#3498db", color: "#3498db", text: "Syncing..." };
      case "offline":
        return { bg: "rgba(241, 196, 15, 0.15)", border: "#f1c40f", color: "#f1c40f", text: "Available Offline" };
      case "sign_in_to_sync":
        return { bg: "rgba(155, 89, 182, 0.15)", border: "#9b59b6", color: "#9b59b6", text: "Sign In to Sync" };
      case "sync_error":
        return { bg: "rgba(231, 76, 60, 0.15)", border: "#e74c3c", color: "#e74c3c", text: "Sync Error" };
      default:
        return { bg: "rgba(255, 255, 255, 0.1)", border: "var(--text-muted)", color: "var(--text-muted)", text: "Local Loaded" };
    }
  };

  const badge = getBadgeStyle();

  return (
    <div
      className="sync-status-bar"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        padding: "8px 16px",
        background: "var(--card-bg, rgba(255, 255, 255, 0.05))",
        borderRadius: "8px",
        marginBottom: "16px",
        fontSize: "0.85rem",
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "3px 10px",
            borderRadius: "12px",
            background: badge.bg,
            border: `1px solid ${badge.border}`,
            color: badge.color,
            fontWeight: 600,
          }}
        >
          ● {badge.text}
        </span>
        {status.pendingCount > 0 && (
          <span style={{ color: "#f39c12", fontWeight: 500 }}>
            ({status.pendingCount} pending {status.pendingCount === 1 ? "change" : "changes"})
          </span>
        )}
        {status.lastSyncTime && (
          <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
            Last sync: {new Date(status.lastSyncTime).toLocaleTimeString()}
          </span>
        )}
      </div>

      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <button
          type="button"
          onClick={handleSyncClick}
          disabled={status.state === "syncing" || !navigator.onLine}
          className="admin-btn"
          style={{
            padding: "4px 10px",
            fontSize: "0.8rem",
            background: "var(--primary-btn-bg, #3498db)",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          {status.state === "syncing" ? "Syncing..." : "Sync Now"}
        </button>

        <button
          type="button"
          onClick={() => setShowClearModal(true)}
          className="admin-btn"
          style={{
            padding: "4px 10px",
            fontSize: "0.8rem",
            background: "rgba(231, 76, 60, 0.2)",
            color: "#e74c3c",
            border: "1px solid #e74c3c",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          Clear Local Data
        </button>
      </div>

      {showClearModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: "#1e1e2e",
              padding: "24px",
              borderRadius: "12px",
              maxWidth: "400px",
              width: "90%",
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            }}
          >
            <h3 style={{ margin: "0 0 12px", color: "#e74c3c" }}>⚠️ Clear Local Movie Data?</h3>
            <p style={{ fontSize: "0.9rem", color: "#ccc", lineHeight: "1.5" }}>
              This action will remove cached movie items from browser storage.
              {status.pendingCount > 0 && (
                <strong style={{ color: "#f39c12", display: "block", marginTop: "8px" }}>
                  Warning: You have {status.pendingCount} un-synced local changes that will be lost!
                </strong>
              )}
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px", marginTop: "20px" }}>
              <button
                type="button"
                onClick={() => setShowClearModal(false)}
                style={{ padding: "8px 16px", borderRadius: "6px", background: "#333", color: "#fff", border: "none", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleClearConfirm}
                style={{ padding: "8px 16px", borderRadius: "6px", background: "#e74c3c", color: "#fff", border: "none", cursor: "pointer", fontWeight: 600 }}
              >
                Clear Data
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
