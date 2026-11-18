import { db } from "../db/cinequeueDb";
import { isObject } from "./syncProtocol";

export async function withSyncLock(
  ownerId: string,
  controller: AbortController,
  action: () => Promise<boolean>,
  options?: { ifAvailable?: boolean }
): Promise<boolean> {
  const signal = controller.signal;
  if (signal.aborted) return false;
  if (navigator.locks) {
    if (options?.ifAvailable) {
      return navigator.locks.request(`cinequeue-sync:${ownerId}`, { ifAvailable: true }, async (lock) => {
        if (!lock || signal.aborted) return false;
        return action();
      });
    }
    return navigator.locks.request(`cinequeue-sync:${ownerId}`, { signal }, async () => {
      if (signal.aborted) return false;
      return action();
    });
  }
  const key = `sync_lease:${ownerId}`;
  const token = crypto.randomUUID();
  const acquire = await db.transaction("rw", db.localMetadata, async () => {
    const lease = (await db.localMetadata.get(key))?.value;
    if (isObject(lease) && Number(lease.expiresAt) > Date.now()) return false;
    await db.localMetadata.put({ key, value: { token, expiresAt: Date.now() + 60000 }, updatedAt: new Date().toISOString() });
    return true;
  });
  if (!acquire) return false;
  let released = false;
  const heartbeat = window.setInterval(() => {
    if (released) return;
    void db.transaction("rw", db.localMetadata, async () => {
      if (released) return;
      const lease = (await db.localMetadata.get(key))?.value;
      if (released) return;
      if (!isObject(lease) || lease.token !== token) throw new Error("Device sync lease was lost.");
      await db.localMetadata.put({ key, value: { token, expiresAt: Date.now() + 60000 }, updatedAt: new Date().toISOString() });
    }).catch((error) => {
      if (released) return;
      console.error("Sync lease renewal failed:", error);
      controller.abort();
    });
  }, 10000);
  try {
    return signal.aborted ? false : await action();
  } finally {
    released = true;
    window.clearInterval(heartbeat);
    await db.transaction("rw", db.localMetadata, async () => {
      const lease = (await db.localMetadata.get(key))?.value;
      if (isObject(lease) && lease.token === token) await db.localMetadata.delete(key);
    });
  }
}
