import "fake-indexeddb/auto";
import Dexie from "dexie";
import { expect, it } from "vitest";
import { CineQueueDatabase } from "./cinequeueDb";

it("migrates legacy movies and payload owners without assigning unknown operations to a login", async () => {
  const name = `migration-${crypto.randomUUID()}`;
  const legacy = new Dexie(name);
  legacy.version(1).stores({
    movies: "id, tmdbId, mediaType, status, watchStatus, rating, ownerId, syncStatus, deletedAt, [ownerId+deletedAt]",
    syncQueue: "operationId, entityType, entityId, status, createdAt, attemptCount",
    localMetadata: "key",
  });
  const migrated = new CineQueueDatabase(name);
  try {
    await legacy.table("movies").put({ id: "movie_1", ownerId: "A", title: "Legacy", rating: 5 });
    await legacy.table("syncQueue").bulkPut([
      { operationId: "owned", entityId: "movie_1", payload: { ownerId: "A" }, status: "pending" },
      { operationId: "unknown", entityId: "movie_1", payload: {}, status: "pending" },
    ]);
    legacy.close();
    await migrated.open();
    expect((await migrated.movies.get(["A", "movie_1"]))?.rating).toBe(5);
    expect((await migrated.syncQueue.get("owned"))?.ownerId).toBe("A");
    expect((await migrated.syncQueue.get("unknown"))?.status).toBe("failed");
    expect((await migrated.syncQueue.get("unknown"))?.ownerId).toBe("");
    await migrated.movies.put({ ...(await migrated.movies.get(["A", "movie_1"]))!, ownerId: "B", rating: 2 });
    expect(await migrated.movies.count()).toBe(2);
  } finally {
    legacy.close();
    await migrated.delete();
  }
});
