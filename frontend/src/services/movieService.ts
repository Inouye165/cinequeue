import { db, type LocalMovie, type SyncOperation } from "../db/cinequeueDb";
import type { RatedMovie, WatchlistItem } from "../types";

export function watchlistItemToLocalMovie(
  item: WatchlistItem,
  ownerId: string
): LocalMovie {
  const tmdbId = item.tmdb_id ?? item.id;
  const isOwned = Boolean(item.is_owned);
  const status = isOwned
    ? "library"
    : item.status === "following"
    ? "following"
    : "queue";

  return {
    id: `${item.media_type || "movie"}_${tmdbId}`,
    tmdbId,
    mediaType: item.media_type || "movie",
    title: item.title || "Untitled",
    overview: item.overview,
    posterPath: item.poster_path || item.poster_url,
    releaseDate: item.release_date,
    status,
    watchStatus: "unwatched",
    rating: item.user_rating || null,
    isOwned,
    createdAt: item.added_at || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    version: 1,
    syncStatus: "synced",
    ownerId,
    localOnly: false,
  };
}

export function localMovieToWatchlistItem(movie: LocalMovie): WatchlistItem {
  const numericId = movie.tmdbId ?? 0;
  return {
    id: numericId,
    tmdb_id: numericId,
    media_type: (movie.mediaType as any) || "movie",
    title: movie.title,
    overview: movie.overview || undefined,
    poster_path: movie.posterPath || undefined,
    poster_url: movie.posterPath || undefined,
    release_date: movie.releaseDate || undefined,
    added_at: movie.createdAt,
    status: movie.status,
    is_owned: movie.isOwned ?? false,
    user_rating: movie.rating || undefined,
  };
}

export const movieService = {
  async getMoviesForOwner(ownerId: string): Promise<LocalMovie[]> {
    try {
      const allMovies = await db.movies
        .where("ownerId")
        .equals(ownerId)
        .toArray();
      return allMovies.filter((m) => !m.deletedAt);
    } catch (err) {
      console.error("IndexedDB read error:", err);
      return [];
    }
  },

  async getWatchlistForOwner(ownerId: string): Promise<WatchlistItem[]> {
    const movies = await this.getMoviesForOwner(ownerId);
    return movies.map(localMovieToWatchlistItem);
  },

  async getRatingsForOwner(ownerId: string): Promise<RatedMovie[]> {
    const movies = await this.getMoviesForOwner(ownerId);
    return movies
      .filter((m) => typeof m.rating === "number" && m.rating > 0)
      .map((m) => ({
        id: m.id,
        media_type: (m.mediaType as any) || "movie",
        tmdb_id: m.tmdbId ?? 0,
        title: m.title,
        poster_path: m.posterPath,
        poster_url: m.posterPath,
        release_date: m.releaseDate,
        rating: m.rating!,
        updated_at: m.updatedAt,
      }));
  },

  async saveMovie(
    movieData: Partial<LocalMovie> & { title: string; tmdbId: number },
    ownerId: string,
    operationType: "upsert" | "delete" | "patch" = "upsert"
  ): Promise<LocalMovie> {
    const id = movieData.id || `${movieData.mediaType || "movie"}_${movieData.tmdbId}`;
    const nowIso = new Date().toISOString();

    const existing = await db.movies.get(id);
    const updatedMovie: LocalMovie = {
      id,
      tmdbId: movieData.tmdbId,
      mediaType: movieData.mediaType || "movie",
      title: movieData.title,
      originalTitle: movieData.originalTitle ?? existing?.originalTitle,
      overview: movieData.overview ?? existing?.overview,
      posterPath: movieData.posterPath ?? existing?.posterPath,
      backdropPath: movieData.backdropPath ?? existing?.backdropPath,
      releaseDate: movieData.releaseDate ?? existing?.releaseDate,
      firstAirDate: movieData.firstAirDate ?? existing?.firstAirDate,
      status: movieData.status ?? existing?.status ?? "queue",
      watchStatus: movieData.watchStatus ?? existing?.watchStatus ?? "unwatched",
      rating: movieData.rating ?? existing?.rating ?? null,
      notes: movieData.notes ?? existing?.notes ?? null,
      priority: movieData.priority ?? existing?.priority ?? null,
      isOwned: movieData.isOwned ?? existing?.isOwned ?? false,
      streamingProviders: movieData.streamingProviders ?? existing?.streamingProviders,
      theatricalAvailability: movieData.theatricalAvailability ?? existing?.theatricalAvailability,
      availabilityUpdatedAt: movieData.availabilityUpdatedAt ?? existing?.availabilityUpdatedAt,
      metadataUpdatedAt: movieData.metadataUpdatedAt ?? existing?.metadataUpdatedAt,
      createdAt: existing?.createdAt || nowIso,
      updatedAt: nowIso,
      deletedAt: operationType === "delete" ? nowIso : undefined,
      version: (existing?.version || 0) + 1,
      syncStatus: "pending_push",
      ownerId,
      localOnly: false,
    };

    await db.movies.put(updatedMovie);

    const op: SyncOperation = {
      operationId: `op_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      entityType: "movie",
      entityId: id,
      operationType,
      payload: updatedMovie,
      createdAt: nowIso,
      attemptCount: 0,
      status: "pending",
    };

    await db.syncQueue.put(op);
    return updatedMovie;
  },

  async deleteMovie(id: string, tmdbId: number, mediaType: string, ownerId: string): Promise<void> {
    await this.saveMovie(
      { id, tmdbId, mediaType, title: "Deleted" },
      ownerId,
      "delete"
    );
  },

  async migrateServerData(
    watchlistItems: WatchlistItem[],
    ratedItems: RatedMovie[],
    ownerId: string
  ): Promise<void> {
    const nowIso = new Date().toISOString();
    for (const item of watchlistItems) {
      const id = `${item.media_type || "movie"}_${item.tmdb_id ?? item.id}`;
      const existing = await db.movies.get(id);
      if (!existing || existing.syncStatus === "synced") {
        const localMovie = watchlistItemToLocalMovie(item, ownerId);
        await db.movies.put(localMovie);
      }
    }

    for (const rate of ratedItems) {
      const id = `${rate.media_type || "movie"}_${rate.tmdb_id}`;
      const existing = await db.movies.get(id);
      if (existing) {
        existing.rating = rate.rating;
        await db.movies.put(existing);
      } else {
        await db.movies.put({
          id,
          tmdbId: rate.tmdb_id,
          mediaType: rate.media_type || "movie",
          title: rate.title,
          posterPath: rate.poster_path || rate.poster_url || undefined,
          releaseDate: rate.release_date || undefined,
          status: "watched",
          watchStatus: "watched",
          rating: rate.rating,
          createdAt: rate.rated_at || nowIso,
          updatedAt: rate.updated_at || nowIso,
          version: 1,
          syncStatus: "synced",
          ownerId,
          localOnly: false,
        });
      }
    }
  },

  async clearLocalData(ownerId?: string): Promise<void> {
    if (ownerId) {
      const userMovies = await db.movies.where("ownerId").equals(ownerId).toArray();
      const ids = userMovies.map((m) => m.id);
      await db.movies.bulkDelete(ids);
    } else {
      await db.movies.clear();
      await db.syncQueue.clear();
    }
  },
};
