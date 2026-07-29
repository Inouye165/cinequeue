import "fake-indexeddb/auto";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
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

    const saved = await db.movies.get("movie_101");
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

    const inDb = await db.movies.get("movie_404");
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
  });
});
