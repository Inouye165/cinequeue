/**
 * PWA Cache Migration Utilities for CineQueue.
 *
 * Removes defective legacy TMDB image cache storage entries while strictly preserving
 * IndexedDB, localStorage, cookies, user authentication, watchlists, ratings, and sync data.
 */

/**
 * Clears legacy TMDB image cache storage entries ("tmdb-images" or starting with "tmdb-images-").
 * Safe to execute when Cache Storage API is unavailable and will never throw errors to prevent app startup.
 */
export async function clearLegacyTmdbImageCache(): Promise<void> {
  try {
    if (typeof window === "undefined" || !("caches" in window) || !window.caches) {
      return;
    }
    const keys = await window.caches.keys();
    for (const key of keys) {
      if (key === "tmdb-images" || key.startsWith("tmdb-images-")) {
        try {
          await window.caches.delete(key);
          console.log(`[PWA Migration] Successfully deleted legacy cache: ${key}`);
        } catch (err) {
          console.warn(`[PWA Migration] Failed to delete legacy cache '${key}':`, err);
        }
      }
    }
  } catch (err) {
    console.warn("[PWA Migration] Error inspecting or clearing legacy TMDB caches:", err);
  }
}

/**
 * Requests an update for existing service worker registrations safely.
 * Will log warnings on failure without throwing or blocking application execution.
 */
export async function requestServiceWorkerUpdate(): Promise<void> {
  try {
    if (
      typeof navigator === "undefined" ||
      !("serviceWorker" in navigator) ||
      !navigator.serviceWorker
    ) {
      return;
    }
    const registrations = await navigator.serviceWorker.getRegistrations();
    for (const reg of registrations) {
      try {
        await reg.update();
        console.log("[PWA Migration] Service worker update requested successfully");
      } catch (err) {
        console.warn("[PWA Migration] Failed to update service worker registration:", err);
      }
    }
  } catch (err) {
    console.warn("[PWA Migration] Error requesting service worker updates:", err);
  }
}
