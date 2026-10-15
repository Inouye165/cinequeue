import "fake-indexeddb/auto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { api } from "../api";
import { __resetFirebaseAuthForTests } from "../context/AuthContext";
import { db } from "../db/cinequeueDb";
import { movieService } from "../services/movieService";

vi.mock("../api", () => ({
  api: {
    firebaseConfig: vi.fn().mockRejectedValue(new Error("Network unavailable")),
    details: vi.fn(), watchlist: vi.fn(), getRatings: vi.fn(),
  },
}));

beforeEach(async () => {
  __resetFirebaseAuthForTests();
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(api.firebaseConfig).mockReset().mockRejectedValue(new Error("Network unavailable"));
  Element.prototype.scrollIntoView = vi.fn();
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  await movieService.clearLocalData();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("opens a saved workspace offline, loads details, persists a rating and survives remount", async () => {
  localStorage.setItem("cinequeue_local_owner", "account-A");
  await movieService.saveMovie({ tmdbId: 101, title: "Saved Film", overview: "Saved overview" }, "account-A");
  await movieService.saveMovie({ tmdbId: 101, title: "Other Account Film" }, "account-B");
  const first = render(<App />);
  await screen.findByRole("heading", { name: "Saved Film" });
  expect(screen.queryByText("Other Account Film")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Open details for Saved Film" }));
  await screen.findByRole("button", { name: "Close details" });
  expect(screen.getAllByText("Saved overview").length).toBeGreaterThan(0);
  expect(api.details).not.toHaveBeenCalled();
  fireEvent.click(screen.getAllByTitle("Rate 4 stars")[0]);
  await waitFor(async () => expect((await db.movies.get(["account-A", "movie_101"]))?.rating).toBe(4));
  expect((await db.movies.get(["account-B", "movie_101"]))?.rating).toBeNull();
  first.unmount();
  render(<App />);
  fireEvent.click(screen.getByRole("tab", { name: "My Ratings" }));
  await screen.findByRole("heading", { name: "Saved Film" });
  expect(api.watchlist).not.toHaveBeenCalled();
  expect(api.getRatings).not.toHaveBeenCalled();
});

it("renders a device-only workspace while cloud startup is unresolved", async () => {
  vi.mocked(api.firebaseConfig).mockReturnValueOnce(new Promise(() => {}));
  await movieService.saveMovie({ tmdbId: 101, title: "Device Film" }, "guest_local");
  render(<App />);
  await screen.findByRole("heading", { name: "Device Film" });
  expect(screen.queryByText("Verifying session…")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Sign in to sync" }));
  await screen.findByRole("button", { name: "Sign in with Google" });
  fireEvent.click(screen.getByRole("button", { name: "Continue on this device" }));
  await screen.findByRole("heading", { name: "Device Film" });
  expect(await db.syncQueue.count()).toBe(0);
});

it("keeps saved movies available when authentication fails and permits offline removal", async () => {
  localStorage.setItem("cinequeue_local_owner", "account-A");
  await movieService.saveMovie({ tmdbId: 101, title: "Saved Film" }, "account-A");
  render(<App />);
  await screen.findByRole("heading", { name: "Saved Film" });
  await screen.findByText(/Cloud connection: Network unavailable/);
  fireEvent.click(screen.getByRole("button", { name: "Options for Saved Film" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));
  await waitFor(async () => expect(await movieService.getMoviesForOwner("account-A")).toEqual([]));
  expect(await db.syncQueue.where("ownerId").equals("account-A").count()).toBe(2);
});
