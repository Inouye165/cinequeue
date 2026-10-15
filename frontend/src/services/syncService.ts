import { liveQuery } from "dexie";
import { db, type SyncOperation } from "../db/cinequeueDb";
import { movieService } from "./movieService";
import { parsePush, parseSnapshot } from "./syncProtocol";
import { withSyncLock } from "./syncLock";

export type SyncState = "available_offline" | "local_loaded" | "offline" |
  "waiting_to_sync" | "syncing" | "synced" | "sign_in_to_sync" | "sync_error" | "conflict";

export interface SyncStatusInfo {
  state: SyncState;
  pendingCount: number;
  conflictCount?: number;
  failedCount?: number;
  lastSyncTime: string | null;
  error?: string | null;
}

class SyncRequestError extends Error {
  constructor(public readonly status: number) {
    super(`Sync request failed (${status})`);
  }
}

export class SyncService {
  private ownerId: string | null = null;
  private workspaceId: string | null = null;
  private generation = 0;
  private controller: AbortController | null = null;
  private running: Promise<boolean> | null = null;
  private retryTimer: number | null = null;
  private listeners = new Set<(status: SyncStatusInfo) => void>();
  private statusInfo: SyncStatusInfo = { state: "available_offline", pendingCount: 0, lastSyncTime: null };

  constructor(private automatic = true) {
    if (automatic) {
      window.addEventListener("online", () => { void this.triggerSync(); });
      window.addEventListener("focus", () => { void this.triggerSync(); });
      window.addEventListener("cinequeue-local-write", () => {
        void this.refreshStatus().then(() => this.triggerSync());
      });
      window.addEventListener("offline", () => {
        this.controller?.abort();
        this.updateStatus({ state: "offline" });
      });
      liveQuery(() => Promise.all([db.syncQueue.toArray(), db.movies.toArray()])).subscribe({
        next: () => { void this.refreshStatus(); },
        error: (error) => this.updateStatus({ state: "sync_error", error: `Device storage unavailable: ${String(error)}` }),
      });
    }
  }

  public setWorkspaceOwner(ownerId: string): void {
    this.workspaceId = ownerId;
    void this.refreshStatus();
  }

  public setAuthenticatedOwner(ownerId: string | null): void {
    if (this.ownerId === ownerId) return;
    this.controller?.abort();
    this.controller = null;
    this.running = null;
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.generation++;
    this.ownerId = ownerId;
    if (ownerId) this.workspaceId = ownerId;
    this.updateStatus({ state: ownerId ? "local_loaded" : "sign_in_to_sync", pendingCount: 0, lastSyncTime: null, error: null });
    void this.refreshStatus();
  }

  public subscribe(listener: (status: SyncStatusInfo) => void): () => void {
    this.listeners.add(listener);
    listener(this.statusInfo);
    return () => this.listeners.delete(listener);
  }
  public getStatus(): SyncStatusInfo { return this.statusInfo; }
  private updateStatus(partial: Partial<SyncStatusInfo>): void {
    this.statusInfo = { ...this.statusInfo, ...partial };
    this.listeners.forEach((listener) => listener(this.statusInfo));
  }
  public async getPendingCount(ownerId = this.workspaceId): Promise<number> {
    if (!ownerId) return 0;
    return db.syncQueue.where("ownerId").equals(ownerId).filter((op) => op.status !== "synced").count();
  }
  private async refreshStatus(): Promise<void> {
    const ownerId = this.workspaceId;
    const generation = this.generation;
    if (!ownerId) return;
    try {
      const ops = await db.syncQueue.where("ownerId").equals(ownerId).toArray();
      const conflicts = await db.movies.where("ownerId").equals(ownerId).filter((movie) => !!movie.remoteConflict).count();
      if (generation !== this.generation || ownerId !== this.workspaceId) return;
      const pending = ops.filter((op) => op.status !== "synced").length;
      this.updateStatus({
        pendingCount: pending, conflictCount: conflicts, failedCount: ops.filter((op) => op.status === "failed").length,
        ...(!this.controller ? { state: conflicts ? "conflict" :
          ownerId === "guest_local" ? "available_offline" :
          !navigator.onLine ? "offline" : !this.ownerId ? "sign_in_to_sync" :
          ops.some((op) => op.status === "failed") ? "sync_error" :
          this.statusInfo.error ? this.statusInfo.state :
          pending ? "waiting_to_sync" : this.statusInfo.state } : {}),
      });
    } catch (error) {
      this.updateStatus({ state: "sync_error", error: `Device storage unavailable: ${String(error)}` });
    }
  }

  public triggerSync(requestedOwner?: string): Promise<boolean> {
    const ownerId = this.ownerId;
    if (!ownerId || ownerId === "guest_local" || (requestedOwner && requestedOwner !== ownerId)) return Promise.resolve(false);
    if (this.running) return this.running;
    if (!navigator.onLine) {
      void this.refreshStatus();
      this.updateStatus({ state: "offline" });
      return Promise.resolve(false);
    }
    const generation = this.generation;
    const controller = new AbortController();
    this.controller = controller;
    let entered = false;
    const run = withSyncLock(ownerId, controller, () => {
      entered = true;
      return this.runSync(ownerId, generation, controller);
    })
      .catch((error) => {
        if (generation === this.generation && !controller.signal.aborted) {
          this.updateStatus({ state: "sync_error", error: String(error) });
        }
        return false;
      }).finally(async () => {
        if (this.running === run) {
          this.running = null;
          this.controller = null;
          await this.refreshStatus();
          try {
            const ready = await db.syncQueue.where("ownerId").equals(ownerId)
              .filter((op) => op.status === "pending" || op.status === "syncing").toArray();
            if (this.statusInfo.state !== "sign_in_to_sync" && this.ownerId === ownerId && navigator.onLine) {
              if (!entered) this.schedule(ownerId, 1000);
              else if (ready.length) this.schedule(ownerId, Math.max(250, Math.min(...ready.map((op) =>
                op.nextAttemptAt ? Date.parse(op.nextAttemptAt) - Date.now() : 250))));
            }
          } catch (error) {
            this.updateStatus({ state: "sync_error", error: `Device storage unavailable: ${String(error)}` });
          }
        }
      });
    this.running = run;
    return run;
  }

  private schedule(ownerId: string, delay: number): void {
    if (!this.automatic || this.ownerId !== ownerId || this.retryTimer !== null) return;
    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      void this.triggerSync(ownerId);
    }, delay);
  }

  private async runSync(ownerId: string, generation: number, controller: AbortController): Promise<boolean> {
    const current = () => generation === this.generation && !controller.signal.aborted;
    const deadline = window.setTimeout(() => controller.abort(), 30000);
    const send = async (url: string, body?: unknown) => {
      const result = await fetch(url, {
        method: body ? "POST" : "GET", credentials: "include", signal: controller.signal,
        headers: { "Content-Type": "application/json", "X-Sync-Owner": ownerId },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!current()) throw new Error("Workspace changed during sync");
      if (!result.ok) {
        if ([401, 403, 409].includes(result.status)) this.updateStatus({ state: "sign_in_to_sync" });
        throw new SyncRequestError(result.status);
      }
      return result.json() as Promise<unknown>;
    };
    let batch: SyncOperation[] = [];
    try {
      this.updateStatus({ state: "syncing", error: null });
      for (let round = 0; round < 10; round++) {
        await db.syncQueue.where("ownerId").equals(ownerId)
          .filter((op) => op.payload.ownerId !== ownerId && op.status !== "failed")
          .modify({ status: "failed", lastError: "Operation payload owner does not match this workspace; upload blocked." });
        const ops = await db.syncQueue.where("ownerId").equals(ownerId).sortBy("createdAt");
        const seen = new Set<string>();
        batch = ops.filter((op) => {
          if (seen.has(op.entityId)) return false;
          seen.add(op.entityId);
          return op.payload.ownerId === ownerId && (op.status === "pending" || op.status === "syncing") &&
            (!op.nextAttemptAt || Date.parse(op.nextAttemptAt) <= Date.now());
        }).slice(0, 50);
        if (!current()) return false;
        if (!batch.length) break;
        await db.transaction("rw", db.syncQueue, async () => {
          for (const op of batch) {
            op.attemptCount++;
            op.lastAttemptAt = new Date().toISOString();
            op.baseRevision ??= "absent";
            op.status = "syncing";
            await db.syncQueue.put(op);
          }
          if (!current()) throw new Error("Workspace changed before push");
        });
        const result = parsePush(await send("/api/sync/movies/push", { protocolVersion: 2, operations: batch }));
        if (!current()) return false;
        const received = new Set<string>();
        for (const op of [...result.applied_operations, ...result.conflicts, ...result.failed_operations]) {
          if (received.has(op.operationId) || !batch.some((sent) => sent.operationId === op.operationId)) {
            throw new Error("Invalid sync acknowledgement operation ID.");
          }
          received.add(op.operationId);
        }
        if (received.size !== batch.length) throw new Error("Incomplete sync acknowledgement; pending changes retained.");
        await db.transaction("rw", db.movies, db.syncQueue, async () => {
          for (const op of batch) {
            const applied = result.applied_operations.find((item) => item.operationId === op.operationId);
            const conflict = result.conflicts.find((item) => item.operationId === op.operationId);
            const failure = result.failed_operations.find((item) => item.operationId === op.operationId);
            const movie = await db.movies.get([ownerId, op.entityId]);
            if (applied) {
              await db.syncQueue.delete(op.operationId);
              // Only unattempted descendants may be rebased; retries keep the original request.
              await db.syncQueue.where("ownerId").equals(ownerId)
                .filter((next) => next.entityId === op.entityId && next.attemptCount === 0)
                .modify({ baseRevision: applied.revision });
              const remaining = await db.syncQueue.where("ownerId").equals(ownerId).filter((next) => next.entityId === op.entityId).count();
              if (movie) await db.movies.update([ownerId, op.entityId], {
                serverRevision: applied.revision,
                syncStatus: remaining || movie.version !== op.payload.version ? "pending_push" : "synced",
              });
            } else if (conflict) {
              if (conflict.entityId !== op.entityId || conflict.remote.id !== op.entityId) throw new Error("Conflict belongs to a different title.");
              if (movie) await db.movies.update([ownerId, op.entityId], { syncStatus: "conflict", remoteConflict: conflict.remote });
              await db.syncQueue.where("ownerId").equals(ownerId)
                .filter((next) => next.entityId === op.entityId).modify({ status: "conflict", lastError: "Choose the device or cloud version." });
            } else if (failure) {
              await db.syncQueue.update(op.operationId, { status: "failed", lastError: failure.reason });
            }
          }
          if (!current()) throw new Error("Workspace changed during acknowledgement");
        });
        batch = [];
      }
      const snapshot = parseSnapshot(await send("/api/sync/movies/pull?protocolVersion=2"));
      if (!current()) return false;
      await movieService.applySnapshot(snapshot.records, ownerId, snapshot.next_cursor, current);
      if (!current()) return false;
      const ops = await db.syncQueue.where("ownerId").equals(ownerId).toArray();
      if (!current()) return false;
      const conflicts = await db.movies.where("ownerId").equals(ownerId).filter((movie) => !!movie.remoteConflict).count();
      const failures = ops.filter((op) => op.status === "failed");
      const pending = ops.length;
      const retry = ops.filter((op) => op.status === "pending" || op.status === "syncing");
      if (retry.length) this.schedule(ownerId, Math.max(250, Math.min(...retry.map((op) => op.nextAttemptAt ? Date.parse(op.nextAttemptAt) - Date.now() : 250))));
      this.updateStatus({
        state: conflicts ? "conflict" : failures.length ? "sync_error" : pending ? "waiting_to_sync" : "synced",
        pendingCount: pending, lastSyncTime: new Date().toISOString(),
        error: failures.length ? failures.map((op) => op.lastError).join("; ") : null,
      });
      window.dispatchEvent(new CustomEvent("cinequeue-data-changed", { detail: { ownerId } }));
      return pending === 0 && conflicts === 0;
    } catch (error) {
      if (generation === this.generation) {
        console.error("Sync failed:", error);
        const delay = Math.min(60000, 1000 * 2 ** Math.min(6, Math.max(0, ...batch.map((op) => op.attemptCount))));
        const rejected = error instanceof SyncRequestError && error.status >= 400 &&
          error.status < 500 && ![401, 403, 408, 409, 429].includes(error.status);
        await db.transaction("rw", db.syncQueue, async () => {
          for (const op of batch) await db.syncQueue.update(op.operationId, {
            status: rejected ? "failed" : "pending", lastError: String(error),
            nextAttemptAt: rejected ? undefined : new Date(Date.now() + delay).toISOString(),
          });
        });
        const signIn = this.statusInfo.state === "sign_in_to_sync";
        this.updateStatus({ state: signIn ? "sign_in_to_sync" : navigator.onLine ? "sync_error" : "offline", error: String(error) });
        if (!signIn && !rejected && navigator.onLine) this.schedule(ownerId, delay);
      }
      return false;
    } finally {
      window.clearTimeout(deadline);
    }
  }

  public async retryFailed(ownerId: string): Promise<boolean> {
    return this.retryOperations(ownerId, "failed");
  }

  public async retryNow(ownerId: string): Promise<boolean> {
    return this.retryOperations(ownerId, "pending");
  }

  private async retryOperations(ownerId: string, status: "failed" | "pending"): Promise<boolean> {
    const generation = this.generation;
    try {
      await db.syncQueue.where("ownerId").equals(ownerId).filter((op) => op.status === status)
        .modify({ status: "pending", nextAttemptAt: undefined });
    } catch (error) {
      console.error("Could not retry device changes:", error);
      if (generation === this.generation && ownerId === this.workspaceId) {
        this.updateStatus({ state: "sync_error", error: `Could not retry device changes: ${String(error)}` });
      }
      return false;
    }
    return this.triggerSync(ownerId);
  }

  public async clearWorkspace(ownerId: string): Promise<void> {
    this.controller?.abort();
    const controller = new AbortController();
    const cleared = await withSyncLock(ownerId, controller, async () => {
      await movieService.clearLocalData(ownerId);
      return true;
    });
    if (!cleared) throw new Error("Another tab is syncing. Try clearing again after it finishes.");
    await this.refreshStatus();
  }
}

export const syncService = new SyncService();
