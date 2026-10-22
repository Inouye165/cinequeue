import { useEffect, useState } from "react";
import { db } from "../db/cinequeueDb";
import { syncService, type SyncStatusInfo } from "../services/syncService";

interface SyncStatusBarProps {
  ownerId: string;
  onDataCleared?: () => void;
}

const VALID_STATUSES = new Set(["queue", "following", "library", "watched"]);
const VALID_FORMATS = new Set(["electronic", "cloud", "hard_copy"]);

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

  // Self-heal or archive legacy 422 failed operations so they never block sync or clutter the UI
  useEffect(() => {
    let active = true;
    const healLegacyFailedOps = async () => {
      try {
        const failedOps = await db.syncQueue
          .where("ownerId")
          .equals(ownerId)
          .filter((op) => op.status === "failed")
          .toArray();
        if (!active || failedOps.length === 0) return;

        const healKey = `cinequeue_healed_${ownerId}`;
        const alreadyHealedOnce = typeof sessionStorage !== "undefined" && sessionStorage.getItem(healKey) === "1";

        await db.transaction("rw", db.syncQueue, db.localMetadata, async () => {
          const nowIso = new Date().toISOString();
          for (const op of failedOps) {
            if (alreadyHealedOnce || (op.attemptCount ?? 0) >= 2) {
              // Archive unrecoverable legacy operation and remove from queue
              await db.localMetadata.put({
                key: `healed_sync:${ownerId}:${op.operationId}`,
                value: { archivedFailedOperation: op },
                updatedAt: nowIso,
              });
              await db.syncQueue.delete(op.operationId);
              continue;
            }

            const payload = { ...op.payload };
            if (op.operationType === "upsert" && payload.deletedAt) {
              delete payload.deletedAt;
            }
            if (!payload.status || !VALID_STATUSES.has(String(payload.status))) {
              payload.status = payload.isOwned ? "library" : "queue";
            }
            if (payload.ownedFormat && !VALID_FORMATS.has(String(payload.ownedFormat))) {
              payload.ownedFormat = "electronic";
            }
            if (typeof payload.rating === "number") {
              const rounded = Math.round(payload.rating);
              payload.rating = rounded >= 1 && rounded <= 5 ? rounded : null;
            }
            await db.syncQueue.update(op.operationId, {
              payload,
              baseRevision: op.baseRevision || "absent",
              status: "pending",
              lastError: null,
              nextAttemptAt: undefined,
            });
          }
        });
        if (typeof sessionStorage !== "undefined") {
          sessionStorage.setItem(healKey, "1");
        }
        void syncService.triggerSync(ownerId);
      } catch {
        // Ignore storage read errors in restricted environments
      }
    };
    void healLegacyFailedOps();
    return () => {
      active = false;
    };
  }, [ownerId, status.state]);

  const handleRetry = () => {
    void syncService.retryFailed(ownerId);
    void syncService.retryNow(ownerId);
  };

  const handleDismissFailed = async () => {
    try {
      await db.syncQueue
        .where("ownerId")
        .equals(ownerId)
        .filter((op) => op.status === "failed")
        .delete();
      setDismissed(true);
      void syncService.triggerSync(ownerId);
    } catch {
      setDismissed(true);
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
