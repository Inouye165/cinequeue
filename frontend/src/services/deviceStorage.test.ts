import "fake-indexeddb/auto";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { db } from "../db/cinequeueDb";
import { movieService } from "./movieService";
import { deviceStorage } from "./deviceStorage";

beforeEach(async () => { await movieService.clearLocalData(); });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("exports only the selected account and restores its immutable outbox and recovery data", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "Private A", rating: 4, notes: "Keep", isOwned: true, ownedFormat: "hard_copy" }, "A");
  await movieService.saveMovie({ tmdbId: 1, title: "Private B" }, "B");
  await db.localMetadata.put({ key: "recovery:A:test", value: { choice: "device", saved: "both versions" }, updatedAt: new Date().toISOString() });
  const [original] = await db.syncQueue.where("ownerId").equals("A").toArray();
  const backup = await deviceStorage.exportBackup("A");
  expect(backup).not.toContain("Private B");
  await movieService.clearLocalData("A");
  expect(await deviceStorage.importBackup(backup, "A")).toBe(1);
  expect((await db.movies.get(["A", "movie_1"]))?.notes).toBe("Keep");
  expect((await db.movies.get(["A", "movie_1"]))?.ownedFormat).toBe("hard_copy");
  expect((await db.syncQueue.get(original.operationId))?.payload).toEqual(original.payload);
  expect((await db.movies.get(["B", "movie_1"]))?.title).toBe("Private B");
  expect(await db.localMetadata.get("recovery:A:test")).toBeDefined();
});

it("restores guest data without ever enqueuing uploads", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "Guest", rating: 5 }, "guest_local");
  const backup = await deviceStorage.exportBackup("guest_local");
  await movieService.clearLocalData("guest_local");
  await deviceStorage.importBackup(backup, "guest_local");
  expect((await db.movies.get(["guest_local", "movie_1"]))?.rating).toBe(5);
  expect(await db.syncQueue.count()).toBe(0);
});

it("rejects malformed, foreign and nonempty restores without changing current data", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
  const backup = await deviceStorage.exportBackup("A");
  await expect(deviceStorage.importBackup(backup, "B")).rejects.toThrow("different workspace");
  await expect(deviceStorage.importBackup(backup, "A")).rejects.toThrow("empty workspace");
  await movieService.clearLocalData("A");
  const bad = JSON.parse(backup);
  bad.movies[0].rating = 10;
  await expect(deviceStorage.importBackup(JSON.stringify(bad), "A")).rejects.toThrow("Invalid backup");
  expect(await db.movies.count()).toBe(0);
});

it("rolls back the entire restore if a storage write fails", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
  const backup = await deviceStorage.exportBackup("A");
  await movieService.clearLocalData("A");
  vi.spyOn(db.syncQueue, "bulkPut").mockRejectedValueOnce(new DOMException("Quota exceeded", "QuotaExceededError"));
  await expect(deviceStorage.importBackup(backup, "A")).rejects.toThrow("Quota exceeded");
  expect(await db.movies.count()).toBe(0);
});

it("restores previously synced records as checked local writes rather than silent cloud overwrites", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "A" }, "A");
  await db.syncQueue.clear();
  await db.movies.update(["A", "movie_1"], { syncStatus: "synced", serverRevision: "old-revision" });
  const backup = await deviceStorage.exportBackup("A");
  await movieService.clearLocalData("A");
  await deviceStorage.importBackup(backup, "A");
  const [op] = await db.syncQueue.toArray();
  expect(op.baseRevision).toBe("old-revision");
  expect(op.status).toBe("pending");
});

it("reports denied persistence and browser quota without inventing durable storage", async () => {
  vi.stubGlobal("navigator", { storage: {
    persisted: vi.fn().mockResolvedValue(false), persist: vi.fn().mockResolvedValue(false),
    estimate: vi.fn().mockResolvedValue({ usage: 900, quota: 1000 }),
  } });
  expect(await deviceStorage.requestPersistence()).toBe(false);
  expect(await deviceStorage.info()).toEqual({ persistent: false, usage: 900, quota: 1000 });
  vi.stubGlobal("navigator", {});
  await expect(deviceStorage.requestPersistence()).rejects.toThrow("cannot request");
});

it("surfaces IndexedDB read failures instead of presenting an empty collection", async () => {
  vi.spyOn(db.movies, "where").mockImplementationOnce(() => { throw new Error("Database unavailable"); });
  await expect(movieService.getMoviesForOwner("A")).rejects.toThrow("Database unavailable");
});

it("enforces the same byte limit on exported backups and restores without deleting device data", async () => {
  await movieService.saveMovie({ tmdbId: 1, title: "Guest" }, "guest_local");
  const size = vi.spyOn(Blob.prototype, "size", "get").mockReturnValue(25 * 1024 * 1024);
  const backup = await deviceStorage.exportBackup("guest_local");
  size.mockReturnValue(25 * 1024 * 1024 + 1);
  await expect(deviceStorage.exportBackup("guest_local")).rejects.toThrow("restore limit");
  await expect(deviceStorage.importBackup(backup, "guest_local")).rejects.toThrow("import limit");
  expect((await db.movies.get(["guest_local", "movie_1"]))?.title).toBe("Guest");
});
