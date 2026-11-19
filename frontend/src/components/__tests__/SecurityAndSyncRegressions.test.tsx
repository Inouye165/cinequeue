import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ActionConfirmationModal, type PendingActionItem } from "../ActionConfirmationModal";
import { DetailModal } from "../DetailModal";
import { SyncStatusBar } from "../SyncStatusBar";
import { db } from "../../db/cinequeueDb";
import { api } from "../../api";
import { movieService } from "../../services/movieService";
import { sportsService } from "../../services/sportsService";
import { syncService } from "../../services/syncService";
import type { MediaDetails } from "../../types";

describe("Security, XSS, and Sync Concurrency Regressions", () => {
  beforeEach(async () => {
    localStorage.clear();
    await movieService.clearLocalData();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("DetailModal sanitizes javascript URLs and invalid trailer keys while preserving safe links", () => {
    const unsafeDetails: MediaDetails = {
      id: 777,
      media_type: "movie",
      title: "Security Film",
      overview: "Testing XSS sanitization.",
      homepage: "https://example.com/security-film",
      release_info: {},
      watch_providers: {
        link: "javascript:alert(1)",
        categories: {},
      },
      reviews: [],
      news: [{ title: "Bad News Link", url: "javascript:alert(2)" }],
      trailers: [{ key: "bad/key?autoplay=1", name: "Injected Trailer" }],
    };

    const { container } = render(
      <DetailModal
        details={unsafeDetails}
        isOnQueue={false}
        isFollowing={false}
        isOwned={false}
        ownedFormat={null}
        watchFreeStreaming={false}
        watchOnSaleBuy={false}
        userRating={null}
        onClose={vi.fn()}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
        onRate={vi.fn()}
        onUpdateOwned={vi.fn()}
        onMoveToFollowing={vi.fn()}
        onMoveToQueue={vi.fn()}
        onUpdateWatchOptions={vi.fn()}
      />
    );

    const links = Array.from(container.querySelectorAll("a"));
    expect(links.every((a) => !(a.getAttribute("href") || "").startsWith("javascript:"))).toBe(true);
    expect(screen.queryByText("View all options on JustWatch")).toBeNull();
    expect(screen.queryByText("Injected Trailer")).toBeNull();

    const homepageLink = links.find((a) => a.getAttribute("href") === "https://example.com/security-film");
    expect(homepageLink).toBeTruthy();
    expect(homepageLink?.getAttribute("target")).toBe("_blank");
    expect(homepageLink?.getAttribute("rel")).toContain("noopener");
    expect(homepageLink?.getAttribute("rel")).toContain("noreferrer");
  });

  it("SyncStatusBar does not auto-heal on mount and dismiss resets local syncStatus under lock", async () => {
    await db.movies.put({
      id: "movie_550",
      ownerId: "user_sync_1",
      tmdbId: 550,
      mediaType: "movie",
      title: "Fight Club",
      status: "queue",
      watchStatus: "unwatched",
      rating: null,
      version: 1,
      createdAt: "2026-10-20T00:00:00.000Z",
      updatedAt: "2026-10-20T00:00:00.000Z",
      syncStatus: "pending_push",
      localOnly: false,
    });
    await db.syncQueue.put({
      operationId: "op_fail_550",
      ownerId: "user_sync_1",
      entityType: "movie",
      entityId: "movie_550",
      operationType: "upsert",
      payload: { tmdbId: 550, mediaType: "movie", title: "Fight Club", status: "queue", ownerId: "user_sync_1" },
      createdAt: "2026-10-20T00:00:00.000Z",
      attemptCount: 1,
      status: "failed",
      lastError: "Rejected",
    });

    vi.spyOn(syncService, "getStatus").mockReturnValue({
      state: "sync_error",
      pendingCount: 1,
      lastSyncTime: null,
      error: "Rejected",
    });
    vi.spyOn(syncService, "subscribe").mockReturnValue(() => {});
    const triggerSpy = vi.spyOn(syncService, "triggerSync").mockResolvedValue(false);

    render(<SyncStatusBar ownerId="user_sync_1" />);

    // Failed op must remain intact until user explicitly acts
    await waitFor(async () => {
      const op = await db.syncQueue.get("op_fail_550");
      expect(op?.status).toBe("failed");
    });

    fireEvent.click(screen.getByRole("button", { name: "Dismiss sync notice" }));

    await waitFor(async () => {
      expect(await db.syncQueue.get("op_fail_550")).toBeUndefined();
      const movie = await db.movies.get(["user_sync_1", "movie_550"]);
      expect(movie?.syncStatus).toBe("synced");
    });
    expect(triggerSpy).toHaveBeenCalledWith("user_sync_1");
  });

  it("ActionConfirmationModal syncs updated proposedItems props and skips invalid tmdb_id 0 items", async () => {
    const itemA: PendingActionItem = {
      id: "a1",
      tmdb_id: 603,
      media_type: "movie",
      title: "The Matrix",
      rating: 5,
      action_type: "rate_movie",
      checked: true,
    };
    const itemB: PendingActionItem = {
      id: "b1",
      tmdb_id: 27205,
      media_type: "movie",
      title: "Inception",
      rating: 4,
      action_type: "rate_movie",
      checked: true,
    };
    const zeroItem: PendingActionItem = {
      id: "bad0",
      tmdb_id: 0,
      media_type: "movie",
      title: "Invalid Zero Title",
      rating: 5,
      action_type: "rate_movie",
      checked: true,
    };

    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ActionConfirmationModal isOpen={true} onClose={vi.fn()} proposedItems={[itemA]} onConfirm={onConfirm} />
    );
    expect(screen.getByText("The Matrix")).toBeTruthy();

    rerender(
      <ActionConfirmationModal
        isOpen={true}
        onClose={vi.fn()}
        proposedItems={[itemB, zeroItem]}
        onConfirm={onConfirm}
      />
    );
    expect(screen.getByText("Inception")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Confirm & Apply/i }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm).toHaveBeenCalledWith([itemB]);
  });

  it("sportsService.syncPreferencesFromServer pushes newer offline local edits upstream", async () => {
    vi.stubGlobal("navigator", { onLine: true });
    localStorage.setItem(
      "sports_prefs:u_sports",
      JSON.stringify({
        streaming_services: ["hulu", "espn_plus"],
        tracked_teams: ["nba_lal"],
        show_in_queue: true,
        setup_completed: true,
        updated_at: "2026-11-18T12:00:00.000Z",
      })
    );

    vi.spyOn(api, "sportsPreferences").mockResolvedValue({
      streaming_services: ["netflix"],
      tracked_teams: [],
      show_in_queue: true,
      setup_completed: true,
      updated_at: "2026-11-17T12:00:00.000Z",
    });
    const saveSpy = vi.spyOn(api, "saveSportsPreferences").mockImplementation(async (prefs) => ({
      streaming_services: prefs.streaming_services ?? [],
      tracked_teams: prefs.tracked_teams ?? [],
      show_in_queue: prefs.show_in_queue ?? true,
      setup_completed: prefs.setup_completed ?? true,
      updated_at: "2026-11-18T12:00:01.000Z",
    }));

    const synced = await sportsService.syncPreferencesFromServer("u_sports");
    expect(saveSpy).toHaveBeenCalledTimes(1);
    expect(synced.streaming_services).toEqual(["hulu", "espn_plus"]);
    expect(synced.tracked_teams).toEqual(["nba_lal"]);
  });
});
