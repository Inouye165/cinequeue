import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  clearLegacyTmdbImageCache,
  requestServiceWorkerUpdate,
} from "../pwaCacheMigration";

describe("pwaCacheMigration", () => {
  const originalCaches = window.caches;
  const originalServiceWorker = navigator.serviceWorker;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    Object.defineProperty(window, "caches", {
      writable: true,
      configurable: true,
      value: originalCaches,
    });
    Object.defineProperty(navigator, "serviceWorker", {
      writable: true,
      configurable: true,
      value: originalServiceWorker,
    });
  });

  describe("clearLegacyTmdbImageCache", () => {
    it("deletes tmdb-images and tmdb-images-* caches while preserving unrelated caches", async () => {
      const deletedCaches: string[] = [];
      const mockCaches = {
        keys: vi.fn().mockResolvedValue([
          "tmdb-images",
          "tmdb-images-v1",
          "workbox-precache-v2",
          "user-watchlist-cache",
        ]),
        delete: vi.fn().mockImplementation(async (key: string) => {
          deletedCaches.push(key);
          return true;
        }),
      };

      Object.defineProperty(window, "caches", {
        writable: true,
        configurable: true,
        value: mockCaches,
      });

      await clearLegacyTmdbImageCache();

      expect(mockCaches.keys).toHaveBeenCalledOnce();
      expect(mockCaches.delete).toHaveBeenCalledWith("tmdb-images");
      expect(mockCaches.delete).toHaveBeenCalledWith("tmdb-images-v1");
      expect(mockCaches.delete).not.toHaveBeenCalledWith("workbox-precache-v2");
      expect(mockCaches.delete).not.toHaveBeenCalledWith("user-watchlist-cache");
      expect(deletedCaches).toEqual(["tmdb-images", "tmdb-images-v1"]);
    });

    it("handles missing Cache Storage support harmlessly", async () => {
      Object.defineProperty(window, "caches", {
        writable: true,
        configurable: true,
        value: undefined,
      });

      await expect(clearLegacyTmdbImageCache()).resolves.not.toThrow();
    });

    it("handles Cache Storage errors safely without preventing startup", async () => {
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const mockCaches = {
        keys: vi.fn().mockRejectedValue(new Error("Cache Storage access denied")),
        delete: vi.fn(),
      };

      Object.defineProperty(window, "caches", {
        writable: true,
        configurable: true,
        value: mockCaches,
      });

      await expect(clearLegacyTmdbImageCache()).resolves.not.toThrow();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });

    it("handles individual cache delete failures gracefully", async () => {
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const mockCaches = {
        keys: vi.fn().mockResolvedValue(["tmdb-images", "tmdb-images-old"]),
        delete: vi.fn().mockRejectedValue(new Error("Failed to delete entry")),
      };

      Object.defineProperty(window, "caches", {
        writable: true,
        configurable: true,
        value: mockCaches,
      });

      await expect(clearLegacyTmdbImageCache()).resolves.not.toThrow();
      expect(mockCaches.delete).toHaveBeenCalledTimes(2);
      expect(consoleWarnSpy).toHaveBeenCalled();
    });
  });

  describe("requestServiceWorkerUpdate", () => {
    it("calls update on all active service worker registrations", async () => {
      const updateMock1 = vi.fn().mockResolvedValue(undefined);
      const updateMock2 = vi.fn().mockResolvedValue(undefined);

      const mockServiceWorker = {
        getRegistrations: vi.fn().mockResolvedValue([
          { update: updateMock1 },
          { update: updateMock2 },
        ]),
      };

      Object.defineProperty(navigator, "serviceWorker", {
        writable: true,
        configurable: true,
        value: mockServiceWorker,
      });

      await requestServiceWorkerUpdate();

      expect(mockServiceWorker.getRegistrations).toHaveBeenCalledOnce();
      expect(updateMock1).toHaveBeenCalledOnce();
      expect(updateMock2).toHaveBeenCalledOnce();
    });

    it("handles missing serviceWorker support harmlessly", async () => {
      Object.defineProperty(navigator, "serviceWorker", {
        writable: true,
        configurable: true,
        value: undefined,
      });

      await expect(requestServiceWorkerUpdate()).resolves.not.toThrow();
    });

    it("handles service worker update errors safely", async () => {
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const mockServiceWorker = {
        getRegistrations: vi.fn().mockRejectedValue(new Error("SW registration failed")),
      };

      Object.defineProperty(navigator, "serviceWorker", {
        writable: true,
        configurable: true,
        value: mockServiceWorker,
      });

      await expect(requestServiceWorkerUpdate()).resolves.not.toThrow();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });

    it("handles individual registration update failures safely", async () => {
      const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const updateFailing = vi.fn().mockRejectedValue(new Error("Update failed"));
      const updateSucceeding = vi.fn().mockResolvedValue(undefined);

      const mockServiceWorker = {
        getRegistrations: vi.fn().mockResolvedValue([
          { update: updateFailing },
          { update: updateSucceeding },
        ]),
      };

      Object.defineProperty(navigator, "serviceWorker", {
        writable: true,
        configurable: true,
        value: mockServiceWorker,
      });

      await requestServiceWorkerUpdate();

      expect(updateFailing).toHaveBeenCalledOnce();
      expect(updateSucceeding).toHaveBeenCalledOnce();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });
  });
});
