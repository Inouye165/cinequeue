import { db, type LocalMovie, type SyncOperation, type SyncRecord } from "../db/cinequeueDb";
import type { MediaDetails, RatedMovie, WatchlistItem } from "../types";
import { formatPosterUrl } from "../utils/mediaUtils";

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
    posterPath: item.poster_path || item.poster_url || undefined,
    releaseDate: item.release_date,
    status,
    watchStatus: "unwatched",
    rating: item.user_rating || null,
    isOwned,
    ownedFormat: item.owned_format,
    watchFreeStreaming: Boolean(item.watch_free_streaming),
    watchOnSaleBuy: Boolean(item.watch_on_sale_buy),
    next_season: item.next_season ?? null,
    seasons: item.seasons ?? null,
    numberOfEpisodes: item.number_of_episodes ?? null,
    numberOfSeasons: item.number_of_seasons ?? null,
    nextEpisodeToAir: item.next_episode_to_air ?? null,
    lastEpisodeToAir: item.last_episode_to_air ?? null,
    showStatus: item.status && !["queue", "following", "library", "watched"].includes(item.status) ? item.status : ((item as any).show_status || (item as any).media_status || null),
    releaseInfo: item.release_info ?? null,
    theatricalAvailability: item.theatrical_release_date ?? null,
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
  const formattedUrl = formatPosterUrl(movie.posterPath);
  return {
    id: numericId,
    tmdb_id: numericId,
    media_type: (movie.mediaType as any) || "movie",
    title: movie.title,
    overview: movie.overview || undefined,
    poster_path: movie.posterPath || undefined,
    poster_url: formattedUrl || movie.posterPath || undefined,
    release_date: movie.releaseDate || undefined,
    theatrical_release_date: movie.theatricalAvailability || undefined,
    added_at: movie.createdAt,
    status: movie.status,
    show_status: movie.showStatus || undefined,
    is_owned: movie.isOwned ?? false,
    owned_format: movie.ownedFormat,
    watch_free_streaming: movie.watchFreeStreaming ?? false,
    watch_on_sale_buy: movie.watchOnSaleBuy ?? false,
    user_rating: movie.rating || undefined,
    next_season: movie.next_season ?? undefined,
    seasons: movie.seasons ?? undefined,
    number_of_episodes: movie.numberOfEpisodes ?? undefined,
    number_of_seasons: movie.numberOfSeasons ?? undefined,
    next_episode_to_air: movie.nextEpisodeToAir ?? undefined,
    last_episode_to_air: movie.lastEpisodeToAir ?? undefined,
    release_info: movie.releaseInfo ?? undefined,
  } as WatchlistItem;
}

const SNAPSHOT_PREFIX = "cinequeue_instant_snapshot:";

function writeInstantSnapshot(ownerId: string, movies: LocalMovie[]): void {
  try {
    if (typeof localStorage === "undefined") return;
    const slim = movies
      .filter((m) => !m.deletedAt)
      .map((m) => ({
        ...m,
        details: undefined, // keep localStorage lightweight; full details live in IndexedDB
      }));
    localStorage.setItem(`${SNAPSHOT_PREFIX}${ownerId}`, JSON.stringify(slim));
  } catch {
    // Ignore storage quota or private-mode errors
  }
}

function readInstantSnapshot(ownerId: string): LocalMovie[] {
  try {
    if (typeof localStorage === "undefined") return [];
    const raw = localStorage.getItem(`${SNAPSHOT_PREFIX}${ownerId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as LocalMovie[]).filter((m) => !m.deletedAt) : [];
  } catch {
    return [];
  }
}

async function refreshOwnerSnapshot(ownerId: string): Promise<void> {
  try {
    const allMovies = await db.movies.where("ownerId").equals(ownerId).toArray();
    writeInstantSnapshot(ownerId, allMovies.filter((m) => !m.deletedAt));
  } catch {
    // Ignore if DB is closing
  }
}

export const movieService = {
  getInstantWatchlist(ownerId: string): WatchlistItem[] {
    return readInstantSnapshot(ownerId).map(localMovieToWatchlistItem);
  },

  getInstantRatings(ownerId: string): RatedMovie[] {
    return readInstantSnapshot(ownerId)
      .filter((m) => typeof m.rating === "number" && m.rating > 0)
      .map((m) => {
        const formattedUrl = formatPosterUrl(m.posterPath);
        return {
          id: m.id,
          media_type: (m.mediaType as any) || "movie",
          tmdb_id: m.tmdbId ?? 0,
          title: m.title,
          poster_path: m.posterPath,
          poster_url: formattedUrl || m.posterPath || undefined,
          release_date: m.releaseDate,
          rating: m.rating!,
          updated_at: m.updatedAt,
        };
      });
  },

  async getMoviesForOwner(ownerId: string): Promise<LocalMovie[]> {
    const allMovies = await db.movies.where("ownerId").equals(ownerId).toArray();
    const active = allMovies.filter((m) => !m.deletedAt);
    writeInstantSnapshot(ownerId, active);
    return active;
  },

  async getWatchlistForOwner(ownerId: string): Promise<WatchlistItem[]> {
    const movies = await this.getMoviesForOwner(ownerId);
    return movies.map(localMovieToWatchlistItem);
  },

  async getRatingsForOwner(ownerId: string): Promise<RatedMovie[]> {
    const movies = await this.getMoviesForOwner(ownerId);
    return movies
      .filter((m) => typeof m.rating === "number" && m.rating > 0)
      .map((m) => {
        const formattedUrl = formatPosterUrl(m.posterPath);
        return {
          id: m.id,
          media_type: (m.mediaType as any) || "movie",
          tmdb_id: m.tmdbId ?? 0,
          title: m.title,
          poster_path: m.posterPath,
          poster_url: formattedUrl || m.posterPath || undefined,
          release_date: m.releaseDate,
          rating: m.rating!,
          updated_at: m.updatedAt,
        };
      });
  },

  async saveMovie(
    movieData: Partial<LocalMovie> & { title: string; tmdbId: number },
    ownerId: string,
    operationType: "upsert" | "delete" | "patch" = "upsert"
  ): Promise<LocalMovie> {
    const id = `${movieData.mediaType || "movie"}_${movieData.tmdbId}`;
    const nowIso = new Date().toISOString();

    const movie = await db.transaction("rw", db.movies, db.syncQueue, db.localMetadata, async () => {
      const existing = await db.movies.get([ownerId, id]);
      const rejected = await db.syncQueue.where("ownerId").equals(ownerId)
        .filter((op) => op.entityId === id && op.status === "failed").toArray();
      for (const op of rejected) {
        await db.localMetadata.put({
          key: `recovery:${ownerId}:${crypto.randomUUID()}`, value: { rejectedOperation: op },
          updatedAt: nowIso,
        });
        await db.syncQueue.delete(op.operationId);
      }
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
        rating:
          movieData.rating !== undefined
            ? movieData.rating && movieData.rating > 0
              ? movieData.rating
              : null
            : existing?.rating ?? null,
        notes: movieData.notes ?? existing?.notes ?? null,
        priority: movieData.priority ?? existing?.priority ?? null,
        isOwned: movieData.isOwned ?? existing?.isOwned ?? false,
        ownedFormat: movieData.ownedFormat ?? existing?.ownedFormat,
        watchFreeStreaming: movieData.watchFreeStreaming ?? existing?.watchFreeStreaming ?? false,
        watchOnSaleBuy: movieData.watchOnSaleBuy ?? existing?.watchOnSaleBuy ?? false,
        streamingProviders: movieData.streamingProviders ?? existing?.streamingProviders,
        theatricalAvailability: movieData.theatricalAvailability ?? existing?.theatricalAvailability,
        availabilityUpdatedAt: movieData.availabilityUpdatedAt ?? existing?.availabilityUpdatedAt,
        metadataUpdatedAt: movieData.metadataUpdatedAt ?? existing?.metadataUpdatedAt,
        next_season: movieData.next_season ?? existing?.next_season ?? null,
        seasons: movieData.seasons ?? existing?.seasons ?? null,
        numberOfEpisodes: movieData.numberOfEpisodes ?? existing?.numberOfEpisodes ?? null,
        numberOfSeasons: movieData.numberOfSeasons ?? existing?.numberOfSeasons ?? null,
        nextEpisodeToAir: movieData.nextEpisodeToAir ?? existing?.nextEpisodeToAir ?? null,
        lastEpisodeToAir: movieData.lastEpisodeToAir ?? existing?.lastEpisodeToAir ?? null,
        showStatus: movieData.showStatus ?? existing?.showStatus ?? null,
        releaseInfo: movieData.releaseInfo ?? existing?.releaseInfo ?? null,
        details: movieData.details ?? existing?.details,
        createdAt: existing?.createdAt || nowIso,
        updatedAt: nowIso,
        deletedAt: operationType === "delete" ? nowIso : undefined,
        version: (existing?.version || 0) + 1,
        syncStatus: existing?.remoteConflict ? "conflict" : "pending_push",
        ownerId,
        localOnly: ownerId === "guest_local",
        serverRevision: existing?.serverRevision,
        remoteConflict: existing?.remoteConflict,
      };
      await db.movies.put(updatedMovie);

      const op: SyncOperation = {
        operationId: `op_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        ownerId,
        entityType: "movie",
        entityId: id,
        operationType,
        payload: updatedMovie,
        createdAt: nowIso,
        attemptCount: 0,
        status: existing?.remoteConflict ? "conflict" : "pending",
        baseRevision: existing?.serverRevision ?? "absent",
      };

      if (!updatedMovie.localOnly) await db.syncQueue.put(op);
      return updatedMovie;
    });
    await refreshOwnerSnapshot(ownerId);
    window.dispatchEvent(new CustomEvent("cinequeue-local-write", { detail: { ownerId } }));
    return movie;
  },

  async deleteMovie(id: string, tmdbId: number, mediaType: string, ownerId: string): Promise<void> {
    const existing = await db.movies.get([ownerId, id]);
    await this.saveMovie(
      { id, tmdbId, mediaType, title: existing?.title ?? "Deleted" },
      ownerId,
      "delete"
    );
  },

  async migrateServerData(
    watchlistItems: WatchlistItem[],
    ratedItems: RatedMovie[],
    ownerId: string,
    isCurrent: () => boolean = () => true
  ): Promise<void> {
    await db.transaction("rw", db.movies, async () => {
      if (!isCurrent()) throw new Error("Workspace changed during import");
      const nowIso = new Date().toISOString();
      for (const item of watchlistItems) {
        const id = `${item.media_type || "movie"}_${item.tmdb_id ?? item.id}`;
        const existing = await db.movies.get([ownerId, id]);
        if (!existing || existing.syncStatus === "synced") {
          const localMovie = watchlistItemToLocalMovie(item, ownerId);
          localMovie.details = existing?.details;
          await db.movies.put(localMovie);
        }
      }

      for (const rate of ratedItems) {
        const id = `${rate.media_type || "movie"}_${rate.tmdb_id}`;
        const existing = await db.movies.get([ownerId, id]);
        if (existing) {
          if (existing.syncStatus !== "synced") continue;
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
      if (!isCurrent()) throw new Error("Workspace changed during import");
    });
    await refreshOwnerSnapshot(ownerId);
  },

  async cacheDetails(ownerId: string, details: MediaDetails): Promise<void> {
    await db.movies.update([ownerId, `${details.media_type}_${details.id}`], {
      details, next_season: details.next_season, seasons: details.seasons,
      numberOfEpisodes: details.number_of_episodes, numberOfSeasons: details.number_of_seasons,
      nextEpisodeToAir: details.next_episode_to_air, lastEpisodeToAir: details.last_episode_to_air,
      showStatus: details.status, releaseInfo: details.release_info,
      theatricalAvailability: details.theatrical_release_date, metadataUpdatedAt: new Date().toISOString(),
    });
    await refreshOwnerSnapshot(ownerId);
  },

  async applySnapshot(
    records: SyncRecord[], ownerId: string, cursor: string, isCurrent: () => boolean
  ): Promise<void> {
    await db.transaction("rw", db.movies, db.syncQueue, db.localMetadata, async () => {
      const now = new Date().toISOString();
      const local = await db.movies.where("ownerId").equals(ownerId).toArray();
      const remoteIds = new Set(records.map((record) => record.id));
      for (const record of records) {
        const existing = await db.movies.get([ownerId, record.id]);
        if (existing?.syncStatus === "conflict") {
          await db.movies.update([ownerId, record.id], { remoteConflict: record });
        } else if (!existing || existing.syncStatus === "synced") {
          await db.movies.put({
            ...existing, ...record, ownerId, localOnly: false,
            watchStatus: record.rating ? "watched" : "unwatched",
            serverRevision: record.revision, remoteConflict: undefined,
            syncStatus: "synced", version: existing?.version ?? 1,
            createdAt: existing?.createdAt ?? now, updatedAt: now,
          });
        }
      }
      for (const movie of local) {
        if (remoteIds.has(movie.id) || movie.localOnly) continue;
        if (movie.syncStatus === "synced") await db.movies.delete([ownerId, movie.id]);
        else if (movie.remoteConflict) {
          await db.movies.update([ownerId, movie.id], {
            remoteConflict: { ...movie.remoteConflict, revision: "absent", deletedAt: now },
          });
        }
      }
      await db.localMetadata.put({ key: `sync_cursor:${ownerId}`, value: cursor, updatedAt: now });
      if (!isCurrent()) throw new Error("Workspace changed during snapshot import");
    });
    await refreshOwnerSnapshot(ownerId);
  },

  async resolveConflict(ownerId: string, id: string, choice: "device" | "cloud"): Promise<void> {
    await db.transaction("rw", db.movies, db.syncQueue, db.localMetadata, async () => {
      const local = await db.movies.get([ownerId, id]);
      const remote = local?.remoteConflict;
      if (!local || !remote) throw new Error("This conflict is no longer available.");
      const now = new Date().toISOString();
      await db.localMetadata.put({
        key: `recovery:${ownerId}:${crypto.randomUUID()}`,
        value: { local, remote, choice }, updatedAt: now,
      });
      await db.syncQueue.where("ownerId").equals(ownerId).filter((op) => op.entityId === id).delete();
      if (choice === "cloud") {
        if (remote.deletedAt) await db.movies.delete([ownerId, id]);
        else await db.movies.put({
          ...local, ...remote, serverRevision: remote.revision, remoteConflict: undefined,
          syncStatus: "synced", updatedAt: now,
          watchStatus: remote.rating ? "watched" : "unwatched",
        });
      } else {
        const movie = { ...local, serverRevision: remote.revision, remoteConflict: undefined, syncStatus: "pending_push" as const };
        await db.movies.put(movie);
        await db.syncQueue.put({
          operationId: crypto.randomUUID(), ownerId, entityType: "movie", entityId: id,
          operationType: movie.deletedAt ? "delete" : "upsert", payload: movie,
          baseRevision: remote.revision, createdAt: now, attemptCount: 0, status: "pending",
        });
      }
    });
    await refreshOwnerSnapshot(ownerId);
    window.dispatchEvent(new CustomEvent("cinequeue-data-changed", { detail: { ownerId } }));
    window.dispatchEvent(new CustomEvent("cinequeue-local-write", { detail: { ownerId } }));
  },

  async getCachedDetails(ownerId: string, mediaType: string, tmdbId: number): Promise<MediaDetails | null> {
    const movie = await db.movies.get([ownerId, `${mediaType}_${tmdbId}`]);
    if (!movie || movie.deletedAt) return null;
    return movie.details ?? {
      ...localMovieToWatchlistItem(movie),
      watch_providers: { categories: {} },
      reviews: [],
      news: [],
      release_info: movie.releaseInfo ?? {},
    };
  },

  async cacheDiscoveryFeed(feedKey: string, items: unknown[]): Promise<void> {
    await db.localMetadata.put({
      key: `discovery_feed:${feedKey}`,
      value: items,
      updatedAt: new Date().toISOString(),
    });
  },

  async getCachedDiscoveryFeed<T = unknown>(feedKey: string): Promise<{ items: T[]; updatedAt: string } | null> {
    const record = await db.localMetadata.get(`discovery_feed:${feedKey}`);
    if (!record || !Array.isArray(record.value)) return null;
    return { items: record.value as T[], updatedAt: record.updatedAt };
  },

  async clearLocalData(ownerId?: string): Promise<void> {
    try {
      if (typeof localStorage !== "undefined") {
        if (ownerId) {
          localStorage.removeItem(`${SNAPSHOT_PREFIX}${ownerId}`);
        } else {
          for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (k && k.startsWith(SNAPSHOT_PREFIX)) {
              localStorage.removeItem(k);
            }
          }
        }
      }
    } catch {
      // Ignore localStorage access errors
    }
    await db.transaction("rw", db.movies, db.syncQueue, db.localMetadata, async () => {
      if (ownerId) {
        const userMovies = await db.movies.where("ownerId").equals(ownerId).toArray();
        const ids: [string, string][] = userMovies.map((m) => [ownerId, m.id]);
        await db.movies.bulkDelete(ids);
        await db.syncQueue.where("ownerId").equals(ownerId).delete();
        await db.localMetadata.delete(`sync_cursor:${ownerId}`);
      } else {
        await db.movies.clear();
        await db.syncQueue.clear();
        await db.localMetadata.clear();
      }
    });
  },
};
