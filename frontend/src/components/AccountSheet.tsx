import { useEffect, useState } from "react";
import { syncService, type SyncStatusInfo } from "../services/syncService";
import { DeviceDataPanel } from "./DeviceDataPanel";
import { syncStatusLabel } from "../utils/syncStatusLabel";

interface AccountSheetProps {
  isOpen: boolean;
  onClose: () => void;
  user?: { email?: string | null; display_name?: string | null; photo_url?: string | null } | null;
  onLogout?: () => void;
  onOpenAgentModal?: (tab: "chat" | "settings" | "logs") => void;
  ownerId: string;
  onDataCleared?: () => void;
  onRequestInstall?: () => void;
}

export function AccountSheet({
  isOpen,
  onClose,
  user,
  onLogout,
  onOpenAgentModal,
  ownerId,
  onDataCleared,
  onRequestInstall,
}: AccountSheetProps) {
  const [syncStatus, setSyncStatus] = useState<SyncStatusInfo>(syncService.getStatus());
  const [showClearModal, setShowClearModal] = useState(false);
  const [clearAccepted, setClearAccepted] = useState(false);
  const [clearError, setClearError] = useState("");

  useEffect(() => {
    const unsubscribe = syncService.subscribe((newStatus) => {
      setSyncStatus(newStatus);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSyncClick = () => {
    void syncService.retryNow(ownerId);
  };

  const handleClearConfirm = async () => {
    try {
      await syncService.clearWorkspace(ownerId);
      setShowClearModal(false);
      onClose();
      if (onDataCleared) onDataCleared();
    } catch (err) { setClearError(String(err)); }
  };

  const getSyncBadge = () => {
    switch (syncStatus.state) {
      case "synced":
        return { text: "Synced", color: "#34d399", bg: "rgba(52, 211, 153, 0.1)" };
      case "syncing":
        return { text: "Syncing...", color: "#38bdf8", bg: "rgba(56, 189, 248, 0.1)" };
      case "offline":
        return { text: "Offline", color: "#facc15", bg: "rgba(250, 204, 21, 0.1)" };
      case "sync_error":
        return { text: "Sync Error", color: "#f87171", bg: "rgba(248, 113, 113, 0.1)" };
      default:
        return { text: "Local", color: "#94a3b8", bg: "rgba(148, 163, 184, 0.1)" };
    }
  };

  const badge = getSyncBadge();

  return (
    <div
      className="account-sheet-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="account-sheet-title"
    >
      <div
        className="account-sheet-container"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="account-sheet-drag-handle" aria-hidden="true" />

        {/* Top Header */}
        <div className="account-sheet-header">
          <div className="account-user-avatar-lg">
            {user?.photo_url ? (
              <img src={user.photo_url} alt={user.display_name || user.email || "User"} />
            ) : (
              <span>{((user?.display_name || user?.email || "U")[0]).toUpperCase()}</span>
            )}
          </div>
          <div className="account-user-details">
            <h3 id="account-sheet-title">{user?.display_name || "CineQueue User"}</h3>
            <p className="account-user-email">{user?.email}</p>
          </div>
          <button
            type="button"
            className="account-sheet-close-btn"
            onClick={onClose}
            aria-label="Close Account Menu"
          >
            ✕
          </button>
        </div>

        {/* Sync Status Section */}
        <div className="account-section sync-section">
          <div className="section-row">
            <span className="section-label">Data Sync Status</span>
            <span className="sync-badge" style={{ color: badge.color, background: badge.bg }}>
              ● {syncStatusLabel(syncStatus.state)}
            </span>
          </div>
          {syncStatus.lastSyncTime && (
            <p className="sync-subtext">
              Last synced: {new Date(syncStatus.lastSyncTime).toLocaleTimeString()}
            </p>
          )}
          <p>{syncStatus.pendingCount} pending changes; {syncStatus.conflictCount ?? 0} conflicting titles.</p>
          {syncStatus.error && <p role="alert">{syncStatus.error}</p>}
          {!!syncStatus.failedCount && <button type="button" onClick={() => void syncService.retryFailed(ownerId)}>Retry rejected changes</button>}
          <button
            type="button"
            className="pill-button secondary full-width"
            onClick={handleSyncClick}
            disabled={syncStatus.state === "syncing" || !navigator.onLine}
          >
            {syncStatus.state === "syncing" ? "Syncing changes..." : "🔄 Sync Now"}
          </button>
        </div>

        {/* AI Agent Features */}
        {onOpenAgentModal && (
          <div className="account-section">
            <span className="section-heading">CineQueue AI Assistant <span style={{ fontSize: "0.75rem", opacity: 0.7, fontWeight: "normal" }}>(AI Calls Disabled in Dev)</span></span>
            <div className="account-menu-list">
              <button
                type="button"
                className="account-menu-btn"
                onClick={() => {
                  onClose();
                  onOpenAgentModal("chat");
                }}
              >
                <span className="menu-btn-icon">💬</span>
                <span className="menu-btn-text">Chat with AI Agent</span>
              </button>
              <button
                type="button"
                className="account-menu-btn"
                onClick={() => {
                  onClose();
                  onOpenAgentModal("settings");
                }}
              >
                <span className="menu-btn-icon">⚙️</span>
                <span className="menu-btn-text">AI Personality & Voice Settings</span>
              </button>
              <button
                type="button"
                className="account-menu-btn"
                onClick={() => {
                  onClose();
                  onOpenAgentModal("logs");
                }}
              >
                <span className="menu-btn-icon">📊</span>
                <span className="menu-btn-text">AI Debugging Logs & Cost</span>
              </button>
            </div>
          </div>
        )}

        {/* Storage & Account Actions */}
        <div className="account-section danger-section">
          <span className="section-heading">Data & Storage</span>
          <DeviceDataPanel ownerId={ownerId} />
          {onRequestInstall && (
            <button
              type="button"
              className="account-menu-btn"
              onClick={onRequestInstall}
            >
              <span className="menu-btn-icon">📲</span>
              <span className="menu-btn-text">Add CineQueue to Home Screen</span>
            </button>
          )}
          <button
            type="button"
            className="account-menu-btn danger"
            onClick={() => { setClearAccepted(false); setClearError(""); setShowClearModal(true); }}
          >
            <span className="menu-btn-icon">🗑️</span>
            <span className="menu-btn-text">Clear Local Data...</span>
          </button>

          {onLogout && (
            <button
              type="button"
              className="account-menu-btn logout"
              onClick={() => {
                onClose();
                onLogout();
              }}
            >
              <span className="menu-btn-icon">🚪</span>
              <span className="menu-btn-text">Sign Out</span>
            </button>
          )}
        </div>
      </div>

      {/* Clear Confirmation Modal */}
      {showClearModal && (
        <div
          className="clear-modal-overlay"
          onClick={() => setShowClearModal(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="clear-modal-title"
        >
          <div className="clear-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 id="clear-modal-title" className="clear-modal-title">
              ⚠️ Clear Local Data?
            </h3>
            <p className="clear-modal-text">
              This removes this workspace's saved titles, ratings and pending edits.
              Device-only data has no cloud copy. Export a backup first.
              {syncStatus.pendingCount > 0 && (
                <strong className="clear-warning">
                  Warning: You have {syncStatus.pendingCount} un-synced local changes that will be lost!
                </strong>
              )}
            </p>
            <label><input type="checkbox" checked={clearAccepted} onChange={(event) => setClearAccepted(event.target.checked)} />
              I have exported a backup or accept losing this workspace's local data.
            </label>
            {clearError && <p role="alert">{clearError}</p>}
            <div className="clear-modal-actions">
              <button
                type="button"
                className="pill-button secondary"
                onClick={() => setShowClearModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="pill-button danger"
                disabled={!clearAccepted}
                onClick={handleClearConfirm}
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
