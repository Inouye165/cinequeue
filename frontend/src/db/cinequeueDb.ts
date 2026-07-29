import Dexie, { type Table } from "dexie";

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
  streamingProviders?: any | null;
  theatricalAvailability?: any | null;
  availabilityUpdatedAt?: string | null;
  metadataUpdatedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string | null;
  version: number;
  syncStatus: "synced" | "pending_push" | "conflict";
  ownerId: string; // user uid / email or "guest_local"
  localOnly: boolean;
}

export interface SyncOperation {
  operationId: string;
  entityType: "movie";
  entityId: string;
  operationType: "upsert" | "delete" | "patch";
  payload: Partial<LocalMovie>;
  createdAt: string;
  attemptCount: number;
  lastAttemptAt?: string | null;
  lastError?: string | null;
  status: "pending" | "syncing" | "synced" | "failed";
}

export interface LocalMetadataRecord {
  key: string;
  value: any;
  updatedAt: string;
}

export class CineQueueDatabase extends Dexie {
  movies!: Table<LocalMovie, string>;
  syncQueue!: Table<SyncOperation, string>;
  localMetadata!: Table<LocalMetadataRecord, string>;

  constructor() {
    super("CineQueueOfflineDB");

    this.version(1).stores({
      movies: "id, tmdbId, mediaType, status, watchStatus, rating, ownerId, syncStatus, deletedAt, [ownerId+deletedAt]",
      syncQueue: "operationId, entityType, entityId, status, createdAt, attemptCount",
      localMetadata: "key",
    });
  }
}

export const db = new CineQueueDatabase();
