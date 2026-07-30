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
  // Debounce interval for sync triggers (ms)
  private static readonly DEBOUNCE_MS = 300;
  private lastTriggerMs = 0;

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
    // Debounce rapid consecutive calls
    const now = Date.now();
    if (now - this.lastTriggerMs < SyncService.DEBOUNCE_MS) {
      return false;
    }
    this.lastTriggerMs = now;
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
          credentials: "include",
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
          // Record the time of a successful push so that UI can display recent sync
          const pushTime = new Date().toISOString();
          localStorage.setItem("cinequeue_last_sync_time", pushTime);
          this.updateStatus({ lastSyncTime: pushTime });
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

      const pullRes = await fetch(url, {
        credentials: "include",
      });
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
        // Update last sync timestamp after a successful pull
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

  /**
   * Initialize UI from cached movies without contacting the server.
   * If movies exist locally, we report a synced state immediately.
   */
  public async initializeFromCache(): Promise<void> {
    try {
      const count = await db.movies.count();
      if (count > 0) {
        this.updateStatus({
          state: "synced",
          pendingCount: await this.getPendingCount(),
          lastSyncTime: localStorage.getItem("cinequeue_last_sync_time"),
        });
      } else {
        this.updateStatus({ state: "available_offline", pendingCount: 0 });
      }
    } catch (e) {
      console.error("Failed to init from cache", e);
    }
  }
}

export const syncService = new SyncService();
