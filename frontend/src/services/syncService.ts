import { db } from "../db/cinequeueDb";
import { movieService } from "./movieService";

export type SyncState =
  | "available_offline"
  | "local_loaded"
  | "offline"
  | "waiting_to_sync"
  | "syncing"
  | "synced"
  | "sign_in_to_sync"
  | "sync_error";

export interface SyncStatusInfo {
  state: SyncState;
  pendingCount: number;
  lastSyncTime: string | null;
  error?: string | null;
}

type SyncListener = (status: SyncStatusInfo) => void;

class SyncService {
  private syncInProgress = false;
  private listeners: Set<SyncListener> = new Set();
  private statusInfo: SyncStatusInfo = {
    state: navigator.onLine ? "synced" : "offline",
    pendingCount: 0,
    lastSyncTime: localStorage.getItem("cinequeue_last_sync_time"),
  };

  constructor() {
    if (typeof window !== "undefined") {
      window.addEventListener("online", () => {
        this.updateStatus({ state: "waiting_to_sync" });
        void this.triggerSync();
      });
      window.addEventListener("offline", () => {
        this.updateStatus({ state: "offline" });
      });
      window.addEventListener("focus", () => {
        void this.triggerSync();
      });
    }
  }

  public subscribe(listener: SyncListener): () => void {
    this.listeners.add(listener);
    listener(this.statusInfo);
    return () => this.listeners.delete(listener);
  }

  public getStatus(): SyncStatusInfo {
    return this.statusInfo;
  }

  private updateStatus(partial: Partial<SyncStatusInfo>): void {
    this.statusInfo = { ...this.statusInfo, ...partial };
    this.listeners.forEach((fn) => fn(this.statusInfo));
  }

  public async getPendingCount(): Promise<number> {
    try {
      const pending = await db.syncQueue
        .where("status")
        .anyOf(["pending", "syncing", "failed"])
        .toArray();
      return pending.length;
    } catch {
      return 0;
    }
  }

  public async triggerSync(ownerId?: string): Promise<boolean> {
    if (this.syncInProgress) return false;
    if (!navigator.onLine) {
      const count = await this.getPendingCount();
      this.updateStatus({ state: "offline", pendingCount: count });
      return false;
    }

    this.syncInProgress = true;
    const pendingCount = await this.getPendingCount();
    this.updateStatus({ state: "syncing", pendingCount });

    try {
      // 1. Push pending operations
      const pendingOps = await db.syncQueue
        .where("status")
        .anyOf(["pending", "failed"])
        .toArray();

      if (pendingOps.length > 0) {
        const res = await fetch("/api/sync/movies/push", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operations: pendingOps }),
        });

        if (res.ok) {
          const data = await res.json();
          const processed: string[] = data.processed_operations || [];
          if (processed.length > 0) {
            await db.syncQueue.bulkDelete(processed);
            for (const opId of processed) {
              const op = pendingOps.find((o) => o.operationId === opId);
              if (op) {
                const m = await db.movies.get(op.entityId);
                if (m) {
                  m.syncStatus = "synced";
                  await db.movies.put(m);
                }
              }
            }
          }
        } else if (res.status === 401 || res.status === 403) {
          this.updateStatus({ state: "sign_in_to_sync" });
          this.syncInProgress = false;
          return false;
        }
      }

      // 2. Pull remote changes
      const lastSync = localStorage.getItem("cinequeue_last_sync_time");
      const url = lastSync
        ? `/api/sync/movies/pull?since_cursor=${encodeURIComponent(lastSync)}`
        : `/api/sync/movies/pull`;

      const pullRes = await fetch(url);
      if (pullRes.ok) {
        const pullData = await pullRes.json();
        if (ownerId && (pullData.watchlist || pullData.ratings)) {
          await movieService.migrateServerData(
            pullData.watchlist || [],
            pullData.ratings || [],
            ownerId
          );
        }
        const nowIso = new Date().toISOString();
        localStorage.setItem("cinequeue_last_sync_time", nowIso);
        const remainingCount = await this.getPendingCount();
        this.updateStatus({
          state: "synced",
          pendingCount: remainingCount,
          lastSyncTime: nowIso,
          error: null,
        });
      }

      this.syncInProgress = false;
      return true;
    } catch (err: any) {
      console.error("Sync failed:", err);
      const remainingCount = await this.getPendingCount();
      this.updateStatus({
        state: "sync_error",
        pendingCount: remainingCount,
        error: err?.message || "Sync failed",
      });
      this.syncInProgress = false;
      return false;
    }
  }
}

export const syncService = new SyncService();
