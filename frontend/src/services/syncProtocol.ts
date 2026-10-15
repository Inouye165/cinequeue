import type { SyncRecord } from "../db/cinequeueDb";

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isSyncRecord(value: unknown): value is SyncRecord {
  if (!isObject(value)) return false;
  return Number.isSafeInteger(value.tmdbId) && Number(value.tmdbId) > 0 &&
    (value.mediaType === "movie" || value.mediaType === "tv") &&
    value.id === `${value.mediaType}_${value.tmdbId}` &&
    typeof value.title === "string" && typeof value.status === "string" &&
    typeof value.revision === "string" && value.revision.length > 0 &&
    (value.rating === null || (Number.isInteger(value.rating) && Number(value.rating) >= 0 && Number(value.rating) <= 5)) &&
    typeof value.isOwned === "boolean" &&
    typeof value.watchFreeStreaming === "boolean" && typeof value.watchOnSaleBuy === "boolean" &&
    (value.ownedFormat === null || value.ownedFormat === "electronic" ||
      value.ownedFormat === "cloud" || value.ownedFormat === "hard_copy") &&
    (value.deletedAt === null || typeof value.deletedAt === "string") &&
    (value.posterPath === null || typeof value.posterPath === "string") &&
    (value.releaseDate === null || typeof value.releaseDate === "string");
}

export function parseSnapshot(value: unknown): { records: SyncRecord[]; next_cursor: string } {
  if (!isObject(value) || value.full_snapshot !== true ||
    typeof value.next_cursor !== "string" || !Array.isArray(value.records) ||
    !value.records.every(isSyncRecord) ||
    new Set(value.records.map((record) => record.id)).size !== value.records.length) {
    throw new Error("Invalid sync snapshot; device data was not changed.");
  }
  return { records: value.records, next_cursor: value.next_cursor };
}

interface PushResult {
  applied_operations: { operationId: string; revision: string }[];
  conflicts: { operationId: string; entityId: string; remote: SyncRecord }[];
  failed_operations: { operationId: string; reason: string }[];
}

export function parsePush(value: unknown): PushResult {
  if (!isObject(value) || !Array.isArray(value.applied_operations) ||
    !Array.isArray(value.conflicts) || !Array.isArray(value.failed_operations)) {
    throw new Error("Invalid sync acknowledgement; pending changes were retained.");
  }
  return {
    applied_operations: value.applied_operations.map((op: unknown) => {
      if (!isObject(op) || typeof op.operationId !== "string" || typeof op.revision !== "string" || !op.revision) {
        throw new Error("Invalid applied sync operation.");
      }
      return { operationId: op.operationId, revision: op.revision };
    }),
    conflicts: value.conflicts.map((op: unknown) => {
      if (!isObject(op) || typeof op.operationId !== "string" || typeof op.entityId !== "string" || !isSyncRecord(op.remote)) {
        throw new Error("Invalid sync conflict.");
      }
      return { operationId: op.operationId, entityId: op.entityId, remote: op.remote };
    }),
    failed_operations: value.failed_operations.map((op: unknown) => {
      if (!isObject(op) || typeof op.operationId !== "string" || typeof op.reason !== "string") throw new Error("Invalid failed sync operation.");
      return { operationId: op.operationId, reason: op.reason };
    }),
  };
}
