import type { SyncState } from "../services/syncService";

export function syncStatusLabel(state: SyncState): string {
  switch (state) {
    case "synced": return "Synced";
    case "syncing": return "Syncing...";
    case "offline": return "Available offline";
    case "available_offline": return "Saved on this device";
    case "sign_in_to_sync": return "Sign in to sync";
    case "sync_error": return "Sync error";
    case "conflict": return "Choose conflicting versions";
    case "waiting_to_sync": return "Waiting to sync";
    default: return "Local collection loaded";
  }
}
