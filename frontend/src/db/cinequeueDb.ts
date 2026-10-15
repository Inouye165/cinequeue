import Dexie, { type Table } from "dexie";
import type { MediaDetails } from "../types";

export interface LocalMovie {
  id: string; // e.g. "movie_1234" or local UUID
  tmdbId?: number | null;
  mediaType: "movie" | "tv" | string;
  title: string;
  originalTitle?: string | null;
  overview?: string | null;
  posterPath?: string | null;
  backdropPath?: string | null;
  releaseDate?: string | null;
  firstAirDate?: string | null;
  status: "queue" | "following" | "library" | "watched" | "archived" | string;
  watchStatus: "unwatched" | "watching" | "watched" | string;
  rating?: number | null;
  notes?: string | null;
  priority?: number | null;
  isOwned?: boolean;
  ownedFormat?: "electronic" | "cloud" | "hard_copy" | null;
  watchFreeStreaming?: boolean;
  watchOnSaleBuy?: boolean;
  streamingProviders?: any | null;
  theatricalAvailability?: any | null;
  availabilityUpdatedAt?: string | null;
  metadataUpdatedAt?: string | null;
  next_season?: any | null;
  seasons?: any[] | null;
  numberOfEpisodes?: number | null;
  numberOfSeasons?: number | null;
  nextEpisodeToAir?: any | null;
  lastEpisodeToAir?: any | null;
  showStatus?: string | null;
  releaseInfo?: any | null;
  details?: MediaDetails;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string | null;
  version: number;
  syncStatus: "synced" | "pending_push" | "conflict";
  ownerId: string; // user uid / email or "guest_local"
  localOnly: boolean;
  serverRevision?: string;
  remoteConflict?: SyncRecord;
}

export interface SyncRecord {
  id: string;
  tmdbId: number;
  mediaType: "movie" | "tv";
  title: string;
  posterPath: string | null;
  releaseDate: string | null;
  status: string;
  isOwned: boolean;
  ownedFormat: "electronic" | "cloud" | "hard_copy" | null;
  watchFreeStreaming: boolean;
  watchOnSaleBuy: boolean;
  rating: number | null;
  revision: string;
  deletedAt: string | null;
}

export interface SyncOperation {
  operationId: string;
  ownerId: string;
  entityType: "movie";
  entityId: string;
  operationType: "upsert" | "delete" | "patch";
  payload: Partial<LocalMovie>;
  createdAt: string;
  attemptCount: number;
  lastAttemptAt?: string | null;
  lastError?: string | null;
  status: "pending" | "syncing" | "synced" | "failed" | "conflict";
  baseRevision?: string;
  nextAttemptAt?: string;
}

export interface LocalMetadataRecord {
  key: string;
  value: unknown;
  updatedAt: string;
}

export class CineQueueDatabase extends Dexie {
  movies: Table<LocalMovie, [string, string]>;
  syncQueue!: Table<SyncOperation, string>;
  localMetadata!: Table<LocalMetadataRecord, string>;

  constructor(name = "CineQueueOfflineDB") {
    super(name);

    this.version(1).stores({
      movies: "id, tmdbId, mediaType, status, watchStatus, rating, ownerId, syncStatus, deletedAt, [ownerId+deletedAt]",
      syncQueue: "operationId, entityType, entityId, status, createdAt, attemptCount",
      localMetadata: "key",
    });
    // Dexie cannot change an existing table's primary key in place.
    this.version(2).stores({
      ownerMovies: "[ownerId+id], ownerId, tmdbId, syncStatus, deletedAt",
      syncQueue: "operationId, ownerId, entityType, entityId, status, createdAt, attemptCount",
    }).upgrade(async (tx) => {
      const movies = await tx.table<LocalMovie>("movies").toArray();
      await tx.table("ownerMovies").bulkPut(movies);
      await tx.table<SyncOperation>("syncQueue").toCollection().modify((op) => {
        // Never guess the owner from the current login or a colliding legacy movie ID.
        op.ownerId = op.payload.ownerId || "";
        if (!op.ownerId) {
          op.status = "failed";
          op.lastError = "Legacy operation has no owner; not eligible for automatic sync.";
        }
      });
    });
    this.version(3).stores({ movies: null });
    this.movies = this.table("ownerMovies");
  }
}

export const db = new CineQueueDatabase();
