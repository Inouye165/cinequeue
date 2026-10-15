import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { db, type SyncRecord } from "../db/cinequeueDb";
import { movieService } from "./movieService";
import { SyncService, syncService } from "./syncService";

const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const record = (overrides: Partial<SyncRecord> = {}): SyncRecord => ({
  id: "movie_1", tmdbId: 1, mediaType: "movie", title: "Remote A", posterPath: null,
  releaseDate: null, status: "queue", isOwned: false, ownedFormat: null,
  watchFreeStreaming: false, watchOnSaleBuy: false, rating: null, revision: "r1", deletedAt: null,
  ...overrides,
});
const snapshot = (records: SyncRecord[] = [], cursor = "cursor") => response({ records, full_snapshot: true, next_cursor: cursor });
const applied = (operationId: string, revision = "r1") => response({
  processed_operations: [operationId], applied_operations: [{ operationId, revision }], conflicts: [], failed_operations: [],
});

describe("account-scoped sync", () => {
  let service: SyncService;
  beforeEach(async () => {
    await movieService.clearLocalData();
    service = new SyncService(false);
    vi.stubGlobal("navigator", { onLine: true });
  });
  afterEach(() => {
    service.setAuthenticatedOwner(null);
    syncService.setAuthenticatedOwner(null);
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each(["retryNow", "retryFailed"] as const)("surfaces storage failures from %s without an unhandled rejection", async (method) => {
    service.setAuthenticatedOwner("A");
    await db.syncQueue.count();
    vi.spyOn(db.syncQueue, "where").mockImplementationOnce(() => { throw new Error("Device database unavailable"); });
    expect(await service[method]("A")).toBe(false);
    expect(service.getStatus().state).toBe("sync_error");
    expect(service.getStatus().error).toContain("Device database unavailable");
  });

  it("pushes only the authorized account and persists its full snapshot cursor", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    await movieService.saveMovie({ tmdbId: 1, title: "B" }, "B");
    const ops = await db.syncQueue.where("ownerId").equals("B").toArray();
    await db.localMetadata.put({ key: "sync_cursor:B", value: "cursor-B", updatedAt: "" });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(applied(ops[0].operationId))
      .mockResolvedValueOnce(snapshot([record({ title: "B" })], "next-B"));
    vi.stubGlobal("fetch", fetchMock);
    service.setAuthenticatedOwner("B");
    expect(await service.triggerSync("A")).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(await service.triggerSync()).toBe(true);
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent.operations.map((op: { ownerId: string }) => op.ownerId)).toEqual(["B"]);
    expect(fetchMock.mock.calls[0][1].headers["X-Sync-Owner"]).toBe("B");
    expect(fetchMock.mock.calls[1][0]).toContain("protocolVersion=2");
    expect((await db.syncQueue.toArray()).map((op) => op.ownerId)).toEqual(["A"]);
    expect((await db.localMetadata.get("sync_cursor:B"))?.value).toBe("next-B");
    expect(await db.localMetadata.get("sync_cursor:A")).toBeUndefined();
  });

  it("discards a delayed pull after an account switch, even if fetch ignores abort", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
    service.setAuthenticatedOwner("A");
    const sync = service.triggerSync();
    await vi.waitFor(() => expect(resolve).toBeDefined());
    service.setAuthenticatedOwner("B");
    resolve(snapshot([record()], "A"));
    expect(await sync).toBe(false);
    expect(await db.movies.count()).toBe(0);
    expect(await db.localMetadata.count()).toBe(0);
    expect(service.getStatus().state).toBe("local_loaded");
  });

  it("preserves pending writes and ignores a late acknowledgement after logout", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    const [op] = await db.syncQueue.toArray();
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
    service.setAuthenticatedOwner("A");
    const sync = service.triggerSync();
    await vi.waitFor(() => expect(resolve).toBeDefined());
    service.setAuthenticatedOwner(null);
    resolve(applied(op.operationId));
    expect(await sync).toBe(false);
    expect(await db.syncQueue.count()).toBe(1);
    expect((await db.movies.get(["A", "movie_1"]))?.syncStatus).toBe("pending_push");
  });

  it("never contacts the cloud without a session or for a device-only workspace", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await service.triggerSync("A")).toBe(false);
    service.setAuthenticatedOwner("guest_local");
    expect(await service.triggerSync()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retains the active account's pending operations when its session is rejected", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 409 })));
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    expect(service.getStatus().state).toBe("sign_in_to_sync");
    expect(await db.syncQueue.count()).toBe(1);
  });

  it("imports the authenticated owner's data on automatic reconnect", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(snapshot([record()], "A-cursor")));
    vi.stubGlobal("fetch", fetchMock);
    syncService.setAuthenticatedOwner("A");
    try {
      window.dispatchEvent(new Event("online"));
      await vi.waitFor(() => expect(syncService.getStatus().state).toBe("synced"));
      expect((await db.movies.get(["A", "movie_1"]))?.title).toBe("Remote A");
      expect(await db.movies.get(["B", "movie_1"])).toBeUndefined();
      expect(fetchMock.mock.calls[0][1].headers["X-Sync-Owner"]).toBe("A");
    } finally {
      syncService.setAuthenticatedOwner(null);
    }
  });

  it("drains changes made during push and rebases only unattempted descendants", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A", rating: 1 }, "A");
    const [first] = await db.syncQueue.toArray();
    let resolve!: (response: Response) => void;
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; }))
      .mockImplementationOnce(async (_url, options) => {
        const body = JSON.parse(options.body);
        expect(body.operations[0].baseRevision).toBe("r1");
        expect(body.operations[0].payload.rating).toBe(5);
        return applied(body.operations[0].operationId, "r2");
      })
      .mockResolvedValueOnce(snapshot([record({ rating: 5, revision: "r2" })]));
    vi.stubGlobal("fetch", fetchMock);
    service.setAuthenticatedOwner("A");
    const run = service.triggerSync();
    await vi.waitFor(() => expect(resolve).toBeDefined());
    const sameRun = service.triggerSync();
    expect(sameRun).toBe(run);
    await movieService.saveMovie({ tmdbId: 1, title: "A", rating: 5 }, "A");
    resolve(applied(first.operationId));
    expect(await run).toBe(true);
    expect(await db.syncQueue.count()).toBe(0);
    expect((await db.movies.get(["A", "movie_1"]))?.rating).toBe(5);
  });

  it("preserves both conflict versions and archives them before explicit resolution", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "Device", rating: 5 }, "A");
    const [op] = await db.syncQueue.toArray();
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response({
        applied_operations: [], failed_operations: [],
        conflicts: [{ operationId: op.operationId, entityId: op.entityId, remote: record({ rating: 2 }) }],
      }))
      .mockResolvedValueOnce(snapshot([record({ rating: 2 })])));
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    expect(service.getStatus().state).toBe("conflict");
    const movie = await db.movies.get(["A", "movie_1"]);
    expect(movie?.rating).toBe(5);
    expect(movie?.remoteConflict?.rating).toBe(2);
    await movieService.resolveConflict("A", "movie_1", "device");
    const [resolved] = await db.syncQueue.toArray();
    expect(resolved.baseRevision).toBe("r1");
    expect(resolved.operationId).not.toBe(op.operationId);
    expect(resolved.payload.rating).toBe(5);
    expect(await db.localMetadata.filter((entry) => entry.key.startsWith("recovery:A:")).count()).toBe(1);
  });

  it("accepting a remote deletion preserves the displaced device version in recovery", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "Device", rating: 5 }, "A");
    await db.movies.update(["A", "movie_1"], { syncStatus: "conflict", remoteConflict: record({ revision: "absent", deletedAt: new Date().toISOString() }) });
    await movieService.resolveConflict("A", "movie_1", "cloud");
    expect(await db.movies.count()).toBe(0);
    expect(await db.syncQueue.count()).toBe(0);
    expect(await db.localMetadata.filter((entry) => entry.key.startsWith("recovery:A:")).count()).toBe(1);
  });

  it("applies full-snapshot deletions and rating clears without deleting pending device edits", async () => {
    for (const id of [1, 2, 3]) await movieService.saveMovie({ tmdbId: id, title: `Film ${id}`, rating: 5 }, "A");
    await db.syncQueue.clear();
    await db.movies.where("ownerId").equals("A").modify({ syncStatus: "synced" });
    await movieService.saveMovie({ tmdbId: 3, title: "Pending", rating: 4 }, "A");
    await movieService.applySnapshot([record({ rating: 0 })], "A", "next", () => true);
    expect((await db.movies.get(["A", "movie_1"]))?.rating).toBe(0);
    expect(await db.movies.get(["A", "movie_2"])).toBeUndefined();
    expect((await db.movies.get(["A", "movie_3"]))?.rating).toBe(4);
  });

  it("never reports synced for rejected operations and preserves their reasons", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    const [op] = await db.syncQueue.toArray();
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response({ applied_operations: [], conflicts: [], failed_operations: [{ operationId: op.operationId, reason: "Invalid rating" }] }))
      .mockResolvedValueOnce(snapshot()));
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    expect(service.getStatus().state).toBe("sync_error");
    expect((await db.syncQueue.get(op.operationId))?.lastError).toBe("Invalid rating");
  });

  it("retains immutable pending operations and backs off after HTTP errors", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    const [original] = await db.syncQueue.toArray();
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    const retry = await db.syncQueue.get(original.operationId);
    expect(retry?.payload).toEqual(original.payload);
    expect(retry?.attemptCount).toBe(1);
    expect(Date.parse(retry!.nextAttemptAt!) - Date.now()).toBeGreaterThan(1000);
    expect(service.getStatus().state).toBe("sync_error");
  });

  it("rejects malformed snapshots rather than clearing device data", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    await db.syncQueue.clear();
    await db.movies.update(["A", "movie_1"], { syncStatus: "synced" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ records: [], next_cursor: "bad" })));
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    expect((await db.movies.get(["A", "movie_1"]))?.title).toBe("A");
    expect(await db.localMetadata.get("sync_cursor:A")).toBeUndefined();
  });

  it("serializes separate workers through the shared IndexedDB lease", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
    service.setAuthenticatedOwner("A");
    const other = new SyncService(false);
    other.setAuthenticatedOwner("A");
    const run = service.triggerSync();
    await vi.waitFor(() => expect(resolve).toBeDefined());
    expect(await other.triggerSync()).toBe(false);
    resolve(snapshot());
    expect(await run).toBe(true);
    other.setAuthenticatedOwner(null);
    expect(await db.localMetadata.get("sync_lease:A")).toBeUndefined();
  });

  it("stops automatic retries for rejected HTTP requests and archives them when the user corrects the title", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "Invalid" }, "A");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 422 })));
    service.setAuthenticatedOwner("A");
    expect(await service.triggerSync()).toBe(false);
    const [rejected] = await db.syncQueue.toArray();
    expect(rejected.status).toBe("failed");
    expect(rejected.nextAttemptAt).toBeUndefined();
    await movieService.saveMovie({ tmdbId: 1, title: "Corrected" }, "A");
    const remaining = await db.syncQueue.toArray();
    expect(remaining).toHaveLength(1);
    expect(remaining[0].operationId).not.toBe(rejected.operationId);
    expect(remaining[0].status).toBe("pending");
    expect(await db.localMetadata.filter((item) => item.key.startsWith("recovery:A:")).count()).toBe(1);
  });

  it("automatically retries transient failures and drains the immutable operation", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    const [op] = await db.syncQueue.toArray();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(applied(op.operationId))
      .mockResolvedValueOnce(snapshot([record()]));
    vi.stubGlobal("fetch", fetchMock);
    syncService.setAuthenticatedOwner("A");
    expect(await syncService.triggerSync()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.waitFor(() => expect(syncService.getStatus().state).toBe("synced"), { timeout: 5000 });
    expect(await db.syncQueue.count()).toBe(0);
    const first = JSON.parse(fetchMock.mock.calls[0][1].body).operations[0];
    const retried = JSON.parse(fetchMock.mock.calls[1][1].body).operations[0];
    expect(retried.payload).toEqual(first.payload);
    expect(retried.operationId).toBe(first.operationId);
    expect(retried.baseRevision).toBe(first.baseRevision);
    expect(retried.attemptCount).toBe(2);
  });

  it("aborts a stalled request at the 30-second deadline without losing its outbox entry", async () => {
    await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const fetchMock = vi.fn((_url, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
      options.signal?.addEventListener("abort", () => reject(new DOMException("Timed out", "AbortError")));
    }));
    vi.stubGlobal("fetch", fetchMock);
    service.setAuthenticatedOwner("A");
    const run = service.triggerSync();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(30000);
    expect(await run).toBe(false);
    expect(await db.syncQueue.count()).toBe(1);
    expect(service.getStatus().state).toBe("sync_error");
    expect(await db.localMetadata.get("sync_lease:A")).toBeUndefined();
  });
});
