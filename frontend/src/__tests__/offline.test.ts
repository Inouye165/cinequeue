import "fake-indexeddb/auto";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { db } from "../db/cinequeueDb";
import { movieService } from "../services/movieService";

describe("Offline Storage & Sync Tests", () => {
  beforeEach(async () => {
    await db.movies.clear();
    await db.syncQueue.clear();
    await db.localMetadata.clear();
  });

  afterEach(async () => {
    await db.movies.clear();
    await db.syncQueue.clear();
  });

  it("1. Saves movie locally to IndexedDB and enqueues sync operation", async () => {
    const movie = await movieService.saveMovie(
      {
        tmdbId: 101,
        mediaType: "movie",
        title: "Inception",
        status: "queue",
      },
      "user_1"
    );

    expect(movie.id).toBe("movie_101");
    expect(movie.syncStatus).toBe("pending_push");

    const saved = await db.movies.get(["user_1", "movie_101"]);
    expect(saved?.title).toBe("Inception");

    const queueOps = await db.syncQueue.toArray();
    expect(queueOps.length).toBe(1);
    expect(queueOps[0].entityId).toBe("movie_101");
  });

  it("2. Reads cached movies for current owner without network", async () => {
    await movieService.saveMovie(
      { tmdbId: 202, mediaType: "movie", title: "Interstellar" },
      "user_1"
    );
    await movieService.saveMovie(
      { tmdbId: 303, mediaType: "movie", title: "Tenet" },
      "user_2"
    );

    const user1Movies = await movieService.getMoviesForOwner("user_1");
    expect(user1Movies.length).toBe(1);
    expect(user1Movies[0].title).toBe("Interstellar");

    const user2Movies = await movieService.getMoviesForOwner("user_2");
    expect(user2Movies.length).toBe(1);
    expect(user2Movies[0].title).toBe("Tenet");
  });

  it("3. Soft-deletes movie locally with deletedAt tombstone", async () => {
    await movieService.saveMovie(
      { tmdbId: 404, mediaType: "movie", title: "Dunkirk" },
      "user_1"
    );

    await movieService.deleteMovie("movie_404", 404, "movie", "user_1");

    const activeMovies = await movieService.getMoviesForOwner("user_1");
    expect(activeMovies.length).toBe(0);

    const inDb = await db.movies.get(["user_1", "movie_404"]);
    expect(inDb?.deletedAt).toBeDefined();
  });

  it("4. Signing out retains cached movies under ownerId", async () => {
    await movieService.saveMovie(
      { tmdbId: 505, mediaType: "movie", title: "The Prestige" },
      "user_1"
    );

    // Simulate logout (reading guest vs logged in user)
    const guestMovies = await movieService.getMoviesForOwner("guest_local");
    expect(guestMovies.length).toBe(0);

    const user1Movies = await movieService.getMoviesForOwner("user_1");
    expect(user1Movies.length).toBe(1);
  });

  it("5. Clearing local data removes user movies explicitly", async () => {
    await movieService.saveMovie(
      { tmdbId: 606, mediaType: "movie", title: "Memento" },
      "user_1"
    );

    await movieService.clearLocalData("user_1");
    const user1Movies = await movieService.getMoviesForOwner("user_1");
    expect(user1Movies.length).toBe(0);
    expect(await db.syncQueue.count()).toBe(0);
  });

  it("isolates the same movie, ratings, imports and deletes across accounts", async () => {
    await movieService.saveMovie({ tmdbId: 101, title: "A", rating: 5 }, "user_1");
    await movieService.saveMovie({ tmdbId: 101, title: "B", rating: 2 }, "user_2");
    await movieService.migrateServerData([], [{ tmdb_id: 101, media_type: "movie", title: "Remote", rating: 1 }], "user_2");
    expect((await movieService.getRatingsForOwner("user_1"))[0].rating).toBe(5);
    expect((await movieService.getRatingsForOwner("user_2"))[0].rating).toBe(2);
    await movieService.deleteMovie("movie_101", 101, "movie", "user_2");
    expect(await movieService.getMoviesForOwner("user_2")).toEqual([]);
    expect((await movieService.getMoviesForOwner("user_1"))[0].title).toBe("A");
    await movieService.clearLocalData("user_2");
    expect((await db.syncQueue.toArray()).map((op) => op.ownerId)).toEqual(["user_1"]);
  });

  it("keeps device-only changes local and supplies details without network", async () => {
    await movieService.saveMovie({ tmdbId: 101, title: "Local", rating: 4 }, "guest_local");
    expect(await db.syncQueue.count()).toBe(0);
    expect((await movieService.getCachedDetails("guest_local", "movie", 101))?.title).toBe("Local");
    expect(await movieService.getCachedDetails("user_1", "movie", 101)).toBeNull();
  });

  it("rolls back the movie if its outbox write fails", async () => {
    const put = vi.spyOn(db.syncQueue, "put").mockRejectedValueOnce(new Error("Storage full"));
    await expect(movieService.saveMovie({ tmdbId: 101, title: "Local" }, "user_1")).rejects.toThrow("Storage full");
    put.mockRestore();
    expect(await db.movies.count()).toBe(0);
  });
});
