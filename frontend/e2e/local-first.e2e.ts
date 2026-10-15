import { expect, test, type Page } from "@playwright/test";

async function seedWorkspace(page: Page, ownerId: string) {
  await page.route("**/api/**", (route) => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Cloud unavailable" }),
  }));
  await page.goto("/");
  await page.getByText(/Device-only workspace:/).waitFor();
  await page.evaluate(async (owner) => {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("CineQueueOfflineDB");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    try {
      const tx = database.transaction(["ownerMovies"], "readwrite");
      const now = new Date().toISOString();
      for (const [uid, title] of [[owner, "Saved Film"], ["account-B", "Private B Film"]]) {
        tx.objectStore("ownerMovies").put({
          ownerId: uid, id: "movie_101", tmdbId: 101, mediaType: "movie", title,
          overview: "Saved offline overview", status: "queue", watchStatus: "unwatched",
          createdAt: now, updatedAt: now, version: 1, syncStatus: "synced",
          localOnly: uid === "guest_local", rating: null,
        });
      }
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
      if (owner !== "guest_local") localStorage.setItem("cinequeue_local_owner", owner);
    } finally {
      database.close();
    }
    await navigator.serviceWorker.ready;
  }, ownerId);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
}

test("offline reload supports saved details, ratings and persistent account isolation", async ({ page, context }) => {
  await seedWorkspace(page, "account-A");
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await expect(page.getByText("Private B Film")).toHaveCount(0);
  await page.getByRole("button", { name: "Open details for Saved Film" }).click();
  await expect(page.getByRole("button", { name: "Close details" })).toBeVisible();
  await page.getByTitle("Rate 4 stars").last().click();
  await expect(page.getByText("4/5").last()).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "My Ratings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await expect(page.getByText("4/5")).toBeVisible();
  await expect(page.getByText("Private B Film")).toHaveCount(0);
});

test("device-only collection remains usable when sign-in is unavailable", async ({ page, context }) => {
  await seedWorkspace(page, "guest_local");
  await context.setOffline(true);
  await page.reload();
  await page.getByRole("button", { name: "Sign in to sync" }).click();
  await expect(page.getByRole("button", { name: "Sign in with Google" })).toBeVisible();
  await page.getByRole("button", { name: "Continue on this device" }).click();
  await page.getByRole("button", { name: "Options for Saved Film" }).click();
  await page.getByRole("menuitem", { name: "Remove", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
  await expect(page.getByText(/Device-only workspace:/)).toBeVisible();
});

test("leaving a saved account offline opens a separate device workspace", async ({ page, context }) => {
  await seedWorkspace(page, "account-A");
  await context.setOffline(true);
  await page.reload();
  await page.getByRole("button", { name: "Use device-only workspace" }).click();
  await expect(page.getByText(/Device-only workspace:/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(/Device-only workspace:/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
});

test("exports and restores a device-only workspace through the actual offline UI", async ({ page, context }) => {
  await seedWorkspace(page, "guest_local");
  await context.setOffline(true);
  await page.getByRole("button", { name: "Open Account menu for This device" }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export workspace backup" }).click();
  const download = await downloaded;
  const backupPath = await download.path();
  expect(backupPath).not.toBeNull();
  await page.getByRole("button", { name: /Clear Local Data\.\.\./ }).click();
  const confirm = page.getByRole("button", { name: "Clear Data", exact: true });
  await expect(confirm).toBeDisabled();
  await page.getByRole("checkbox", { name: /I have exported a backup/ }).check();
  await confirm.click();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Open Account menu for This device" }).click();
  await page.getByLabel("Restore workspace backup", { exact: true }).setInputFiles(backupPath!);
  await expect(page.getByText("Restored 1 titles. Cloud changes will be checked before upload.")).toBeVisible();
  await page.getByRole("button", { name: "Close Account Menu" }).click();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await expect(page.getByText("Private B Film")).toHaveCount(0);
});

test("resolves a saved conflict explicitly and retains both versions in the backup", async ({ page, context }) => {
  await seedWorkspace(page, "account-A");
  await page.evaluate(async () => {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("CineQueueOfflineDB");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const tx = database.transaction("ownerMovies", "readwrite");
    const store = tx.objectStore("ownerMovies");
    const request = store.get(["account-A", "movie_101"]);
    request.onsuccess = () => store.put({
      ...request.result, rating: 5, syncStatus: "conflict",
      remoteConflict: {
        id: "movie_101", tmdbId: 101, mediaType: "movie", title: "Saved Film",
        posterPath: null, releaseDate: null, status: "watched", isOwned: false,
        ownedFormat: null, watchFreeStreaming: false, watchOnSaleBuy: false,
        rating: 2, revision: "remote-revision", deletedAt: null,
      },
    });
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onabort = () => reject(tx.error);
    });
    database.close();
  });
  await context.setOffline(true);
  await page.reload();
  await page.getByRole("button", { name: "Open Account menu for Saved account workspace" }).click();
  await expect(page.getByText("Saved Film: choose a version")).toBeVisible();
  await page.getByRole("button", { name: "Keep cloud version" }).click();
  await expect(page.getByText("Saved Film: choose a version")).toHaveCount(0);
  await page.getByRole("button", { name: "Close Account Menu" }).click();
  await page.getByRole("tab", { name: "My Ratings", exact: true }).click();
  await expect(page.getByText("2/5")).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "My Ratings", exact: true }).click();
  await expect(page.getByText("2/5")).toBeVisible();
  const archived = await page.evaluate(async () => {
    const database = await new Promise<IDBDatabase>((resolve) => {
      const request = indexedDB.open("CineQueueOfflineDB");
      request.onsuccess = () => resolve(request.result);
    });
    const tx = database.transaction("localMetadata", "readonly");
    const result = await new Promise<{ key: string; value: { local: { rating: number }; remote: { rating: number } } }[]>((resolve) => {
      const request = tx.objectStore("localMetadata").getAll();
      request.onsuccess = () => resolve(request.result);
    });
    database.close();
    return result.filter((entry) => entry.key.startsWith("recovery:account-A:")).map((entry) => [entry.value.local.rating, entry.value.remote.rating]);
  });
  expect(archived).toEqual([[5, 2]]);
});

test("updates a second tab when a device-only rating is saved without cloud sync", async ({ page, context }) => {
  await seedWorkspace(page, "guest_local");
  const second = await context.newPage();
  await second.route("**/api/**", (route) => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Cloud unavailable" }),
  }));
  await second.goto("/");
  await expect(second.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await second.getByRole("tab", { name: "My Ratings", exact: true }).click();
  await expect(second.getByRole("heading", { name: "Saved Film", exact: true })).toHaveCount(0);
  await page.getByTitle("Rate 4 stars").last().click();
  await expect(second.getByRole("heading", { name: "Saved Film", exact: true })).toBeVisible();
  await expect(second.getByText("4/5")).toBeVisible();
  await second.reload();
  await second.getByRole("tab", { name: "My Ratings", exact: true }).click();
  await expect(second.getByText("4/5")).toBeVisible();
  await second.close();
});
