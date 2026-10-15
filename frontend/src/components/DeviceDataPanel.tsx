import { useEffect, useState } from "react";
import { liveQuery } from "dexie";
import { db, type LocalMovie } from "../db/cinequeueDb";
import { deviceStorage } from "../services/deviceStorage";
import { movieService } from "../services/movieService";
import { syncService } from "../services/syncService";
import { withSyncLock } from "../services/syncLock";

export function DeviceDataPanel({ ownerId }: { ownerId: string }) {
  const [info, setInfo] = useState<Awaited<ReturnType<typeof deviceStorage.info>> | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflicts, setConflicts] = useState<LocalMovie[]>([]);
  useEffect(() => {
    let active = true;
    void deviceStorage.info().then((value) => { if (active) setInfo(value); })
      .catch((err) => { if (active) setError(String(err)); });
    const subscription = liveQuery(() => db.movies.where("ownerId").equals(ownerId)
      .filter((movie) => !!movie.remoteConflict).toArray()).subscribe({
      next: setConflicts, error: (err) => setError(`Device storage unavailable: ${String(err)}`),
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, [ownerId]);

  const perform = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setMessage("");
    try { await action(); } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };
  const exportBackup = () => perform(async () => {
    const text = await deviceStorage.exportBackup(ownerId);
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `cinequeue-backup-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage("Backup download started. Keep this private file somewhere safe.");
  });
  return (
    <section aria-label="Device storage and recovery">
      <p>
        {info?.persistent ? "Persistent storage enabled." :
          info?.persistent === false ? "Browser may evict device data. Export a backup." :
          "Storage protection is unavailable in this browser. Export a backup."}
        {info?.quota ? ` Using ${((info.usage ?? 0) / 1048576).toFixed(1)} of ${(info.quota / 1048576).toFixed(0)} MB.` : ""}
      </p>
      {info?.quota && (info.usage ?? 0) / info.quota >= 0.8 && <p role="alert">Device storage is nearly full. Export a backup before making more changes.</p>}
      <button type="button" className="pill-button secondary" disabled={busy || info?.persistent === true} onClick={() => void perform(async () => {
        const granted = await deviceStorage.requestPersistence();
        setInfo(await deviceStorage.info());
        setMessage(granted ? "Persistent storage enabled. Backups are still necessary." : "Browser did not grant persistent storage. Export a backup to protect your collection.");
      })}>Protect device storage</button>
      <button type="button" className="pill-button secondary" disabled={busy} onClick={() => void exportBackup()}>Export workspace backup</button>
      <label>
        Restore workspace backup
        <input type="file" accept=".json,application/json" disabled={busy} onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (!file) return;
          void perform(async () => {
            if (file.size > 25 * 1024 * 1024) throw new Error("Backup exceeds the 25 MB import limit.");
            const text = await file.text();
            let count = 0;
            const restored = await withSyncLock(ownerId, new AbortController(), async () => {
              count = await deviceStorage.importBackup(text, ownerId);
              return true;
            });
            if (!restored) throw new Error("Another tab is syncing. Try restoring after it finishes.");
            setMessage(`Restored ${count} titles. Cloud changes will be checked before upload.`);
            setInfo(await deviceStorage.info());
          });
        }} />
      </label>
      <p>Restore is owner-scoped and requires an empty workspace. Backups contain private collection data, pending edits and recovery versions. Online details can be refreshed after restore.</p>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {conflicts.map((movie) => (
        <section key={movie.id} aria-label={`Resolve conflict for ${movie.title}`}>
          <h4>{movie.title}: choose a version</h4>
          <p>Device: {movie.deletedAt ? "Deleted" : `${movie.status}, rating ${movie.rating ?? 0}/5, ${movie.isOwned ? "owned" : "not owned"}`}</p>
          <p>Cloud: {movie.remoteConflict?.deletedAt ? "Deleted" : `${movie.remoteConflict?.status}, rating ${movie.remoteConflict?.rating ?? 0}/5, ${movie.remoteConflict?.isOwned ? "owned" : "not owned"}`}</p>
          <p>Both versions will remain in the recovery section of your exported backup.</p>
          {(["device", "cloud"] as const).map((choice) => (
            <button key={choice} type="button" className="pill-button secondary" disabled={busy} onClick={() => void perform(async () => {
              await movieService.resolveConflict(ownerId, movie.id, choice);
              void syncService.triggerSync(ownerId);
            })}>Keep {choice} version</button>
          ))}
        </section>
      ))}
    </section>
  );
}
