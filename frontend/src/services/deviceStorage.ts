import { db, type LocalMovie, type SyncOperation, type LocalMetadataRecord } from "../db/cinequeueDb";
import { isObject, isSyncRecord } from "./syncProtocol";

const MAX_BACKUP_BYTES = 25 * 1024 * 1024;
const error = () => new Error("Invalid backup. No device data was changed.");
const optionalString = (value: unknown): string | null | undefined => {
  if (value === undefined || value === null || typeof value === "string") return value;
  throw error();
};

function parseMovie(value: unknown, ownerId: string): LocalMovie {
  if (!isObject(value) || value.ownerId !== ownerId ||
    !Number.isSafeInteger(value.tmdbId) || Number(value.tmdbId) <= 0 ||
    (value.mediaType !== "movie" && value.mediaType !== "tv") ||
    value.id !== `${value.mediaType}_${value.tmdbId}` ||
    typeof value.title !== "string" || typeof value.status !== "string" ||
    typeof value.watchStatus !== "string" || !Number.isSafeInteger(value.version) || Number(value.version) < 1 ||
    typeof value.createdAt !== "string" || !Number.isFinite(Date.parse(value.createdAt)) ||
    typeof value.updatedAt !== "string" || !Number.isFinite(Date.parse(value.updatedAt)) ||
    !["synced", "pending_push", "conflict"].includes(String(value.syncStatus)) ||
    typeof value.localOnly !== "boolean" || value.localOnly !== (ownerId === "guest_local") ||
    (value.rating !== undefined && value.rating !== null &&
      (!Number.isInteger(value.rating) || Number(value.rating) < 0 || Number(value.rating) > 5)) ||
    (value.remoteConflict !== undefined && (!isSyncRecord(value.remoteConflict) || value.remoteConflict.id !== value.id))) throw error();
  for (const key of ["isOwned", "watchFreeStreaming", "watchOnSaleBuy"]) {
    if (value[key] !== undefined && typeof value[key] !== "boolean") throw error();
  }
  if (value.ownedFormat !== undefined && value.ownedFormat !== null &&
    value.ownedFormat !== "electronic" && value.ownedFormat !== "cloud" && value.ownedFormat !== "hard_copy") throw error();
  if (value.priority !== undefined && value.priority !== null && typeof value.priority !== "number") throw error();
  const syncStatus = value.syncStatus;
  if (syncStatus !== "synced" && syncStatus !== "pending_push" && syncStatus !== "conflict") throw error();
  // Restore user data, not executable/untrusted API cache structures.
  return {
    id: String(value.id), ownerId, tmdbId: Number(value.tmdbId), mediaType: value.mediaType,
    title: value.title, status: value.status, watchStatus: value.watchStatus,
    version: Number(value.version), createdAt: value.createdAt, updatedAt: value.updatedAt,
    syncStatus, localOnly: value.localOnly,
    rating: value.rating === undefined || value.rating === null ? null : Number(value.rating),
    isOwned: value.isOwned === true, watchFreeStreaming: value.watchFreeStreaming === true,
    watchOnSaleBuy: value.watchOnSaleBuy === true,
    ownedFormat: value.ownedFormat === "electronic" || value.ownedFormat === "cloud" || value.ownedFormat === "hard_copy" ? value.ownedFormat : null,
    notes: optionalString(value.notes), priority: value.priority == null ? null : Number(value.priority),
    posterPath: optionalString(value.posterPath), releaseDate: optionalString(value.releaseDate),
    firstAirDate: optionalString(value.firstAirDate), originalTitle: optionalString(value.originalTitle),
    overview: optionalString(value.overview), deletedAt: optionalString(value.deletedAt),
    serverRevision: optionalString(value.serverRevision) ?? undefined,
    remoteConflict: isSyncRecord(value.remoteConflict) ? value.remoteConflict : undefined,
  };
}

function parseOperation(value: unknown, ownerId: string): SyncOperation {
  if (!isObject(value) || value.ownerId !== ownerId || typeof value.operationId !== "string" || !value.operationId ||
    typeof value.entityId !== "string" || value.entityType !== "movie" ||
    (value.operationType !== "upsert" && value.operationType !== "patch" && value.operationType !== "delete") ||
    !Number.isSafeInteger(value.attemptCount) || Number(value.attemptCount) < 0 ||
    typeof value.createdAt !== "string" || !Number.isFinite(Date.parse(value.createdAt)) ||
    (value.status !== "pending" && value.status !== "syncing" && value.status !== "synced" && value.status !== "failed" && value.status !== "conflict")) throw error();
  const payload = parseMovie(value.payload, ownerId);
  if (payload.id !== value.entityId) throw error();
  // Receipts depend on the original immutable payload, including its cached metadata.
  if (!isObject(value.payload)) throw error();
  return {
    operationId: value.operationId, ownerId, entityId: value.entityId, entityType: "movie",
    operationType: value.operationType, payload: value.payload,
    createdAt: value.createdAt, attemptCount: Number(value.attemptCount), status: value.status,
    baseRevision: optionalString(value.baseRevision) ?? "absent",
    lastAttemptAt: optionalString(value.lastAttemptAt), lastError: optionalString(value.lastError),
    nextAttemptAt: optionalString(value.nextAttemptAt) ?? undefined,
  };
}

export const deviceStorage = {
  async info(): Promise<{ persistent: boolean | null; usage?: number; quota?: number }> {
    if (!navigator.storage) return { persistent: null };
    const persistent = navigator.storage.persisted ? await navigator.storage.persisted() : null;
    const estimate = navigator.storage.estimate ? await navigator.storage.estimate() : {};
    return { persistent, usage: estimate.usage, quota: estimate.quota };
  },
  async requestPersistence(): Promise<boolean> {
    if (!navigator.storage?.persist) throw new Error("This browser cannot request persistent storage. Export a backup instead.");
    return navigator.storage.persist();
  },
  async exportBackup(ownerId: string): Promise<string> {
    const backup = await db.transaction("r", db.movies, db.syncQueue, db.localMetadata, async () => ({
      format: "cinequeue-device-backup", version: 1, ownerId, exportedAt: new Date().toISOString(),
      movies: await db.movies.where("ownerId").equals(ownerId).toArray(),
      operations: await db.syncQueue.where("ownerId").equals(ownerId).toArray(),
      recovery: await db.localMetadata.filter((item) => item.key.startsWith(`recovery:${ownerId}:`)).toArray(),
    }));
    const text = JSON.stringify(backup, null, 2);
    if (new Blob([text]).size > MAX_BACKUP_BYTES) {
      throw new Error("Workspace backup exceeds the 25 MB restore limit. No incomplete backup was exported.");
    }
    return text;
  },
  async importBackup(text: string, ownerId: string): Promise<number> {
    if (new Blob([text]).size > MAX_BACKUP_BYTES) throw new Error("Backup exceeds the 25 MB import limit.");
    const value: unknown = JSON.parse(text);
    if (!isObject(value) || value.format !== "cinequeue-device-backup" || value.version !== 1 ||
      value.ownerId !== ownerId || !Array.isArray(value.movies) || !Array.isArray(value.operations) ||
      !Array.isArray(value.recovery)) throw new Error("Backup is invalid or belongs to a different workspace. No data was changed.");
    const movies = value.movies.map((movie: unknown) => parseMovie(movie, ownerId));
    const operations = value.operations.map((op: unknown) => parseOperation(op, ownerId));
    const recovery: LocalMetadataRecord[] = value.recovery.map((item: unknown) => {
      if (!isObject(item) || typeof item.key !== "string" || !item.key.startsWith(`recovery:${ownerId}:`) ||
        typeof item.updatedAt !== "string") throw error();
      return { key: item.key, value: item.value, updatedAt: item.updatedAt };
    });
    if (new Set(movies.map((movie) => movie.id)).size !== movies.length ||
      new Set(operations.map((op) => op.operationId)).size !== operations.length ||
      operations.some((op) => !movies.some((movie) => movie.id === op.entityId)) ||
      (ownerId === "guest_local" && operations.length)) throw error();
    await db.transaction("rw", db.movies, db.syncQueue, db.localMetadata, async () => {
      // Import only into an empty workspace; existing data is never overwritten.
      if (await db.movies.where("ownerId").equals(ownerId).count() ||
        await db.syncQueue.where("ownerId").equals(ownerId).count()) {
        throw new Error("Restore requires an empty workspace. Export current data before clearing it.");
      }
      for (const op of operations) {
        if (await db.syncQueue.get(op.operationId)) throw new Error("Backup operation ID collides with existing device data.");
      }
      for (const movie of movies) {
        if (!movie.localOnly && !operations.some((op) => op.entityId === movie.id) && !movie.remoteConflict) {
          movie.syncStatus = "pending_push";
          operations.push({
            operationId: crypto.randomUUID(), ownerId, entityType: "movie", entityId: movie.id,
            operationType: movie.deletedAt ? "delete" : "upsert", payload: movie,
            baseRevision: movie.serverRevision ?? "absent",
            createdAt: new Date().toISOString(), attemptCount: 0, status: "pending",
          });
        }
      }
      await db.movies.bulkPut(movies);
      await db.syncQueue.bulkPut(operations);
      await db.localMetadata.bulkPut(recovery);
    });
    window.dispatchEvent(new CustomEvent("cinequeue-data-changed", { detail: { ownerId } }));
    window.dispatchEvent(new CustomEvent("cinequeue-local-write", { detail: { ownerId } }));
    return movies.length;
  },
};
