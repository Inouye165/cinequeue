import { useEffect, useState } from "react";
import { db } from "../db/cinequeueDb";
import { withSyncLock } from "../services/syncLock";
import { syncService, type SyncStatusInfo } from "../services/syncService";

interface SyncStatusBarProps {
  ownerId: string;
  onDataCleared?: () => void;
}

export function SyncStatusBar({ ownerId }: SyncStatusBarProps) {
  const [status, setStatus] = useState<SyncStatusInfo>(syncService.getStatus());
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const unsubscribe = syncService.subscribe((newStatus) => {
      setStatus(newStatus);
      if (newStatus.state === "synced") {
        setDismissed(false);
      }
    });
    return unsubscribe;
  }, []);

  const handleRetry = () => {
    void syncService.retryFailed(ownerId);
    void syncService.retryNow(ownerId);
  };

  const handleDismissFailed = async () => {
    try {
      let completed = false;
      await withSyncLock(
        ownerId,
        new AbortController(),
        async () => {
          await db.transaction("rw", db.movies, db.syncQueue, async () => {
            const failedOps = await db.syncQueue
              .where("ownerId")
              .equals(ownerId)
              .filter((op) => op.status === "failed")
              .toArray();
            const entityIds = Array.from(new Set(failedOps.map((op) => op.entityId)));
            await db.syncQueue
              .where("ownerId")
              .equals(ownerId)
              .filter((op) => op.status === "failed")
              .delete();
            for (const entityId of entityIds) {
              const remaining = await db.syncQueue
                .where("ownerId")
                .equals(ownerId)
                .filter((op) => op.entityId === entityId)
                .count();
              if (remaining === 0) {
                await db.movies.update([ownerId, entityId], { syncStatus: "synced" });
              }
            }
          });
          completed = true;
          return true;
        },
        { ifAvailable: true }
      );
      if (completed) {
        setDismissed(true);
        void syncService.triggerSync(ownerId);
      }
    } catch {
      // Leave sync notice intact if storage or lock acquisition failed
    }
  };

  // Hide completely during normal operation (Google/Meta apps sync silently)
  if (
    dismissed ||
    status.state === "synced" ||
    status.state === "local_loaded" ||
    status.state === "available_offline" ||
    status.state === "sign_in_to_sync" ||
    status.state === "offline"
  ) {
    return null;
  }

  if (status.state === "syncing" || status.state === "waiting_to_sync") {
    return (
      <div className="sync-pill-toast syncing" role="status" aria-live="polite">
        <span className="sync-spinner-dot" aria-hidden="true" />
        <span>Syncing changes…</span>
      </div>
    );
  }

  return (
    <div className="sync-pill-toast warning" role="status" aria-live="polite">
      <span className="sync-pill-message">
        {status.state === "conflict"
          ? "Sync conflict detected — open Account menu to resolve"
          : `${status.pendingCount || 1} local change${status.pendingCount === 1 ? "" : "s"} pending sync`}
      </span>
      <div className="sync-pill-actions">
        <button type="button" className="sync-pill-btn primary" onClick={handleRetry}>
          Retry
        </button>
        <button
          type="button"
          className="sync-pill-btn subtle"
          onClick={() => void handleDismissFailed()}
          aria-label="Dismiss sync notice"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
