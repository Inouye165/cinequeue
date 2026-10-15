import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AccountSheet } from "../AccountSheet";
import { movieService } from "../../services/movieService";

vi.mock("../DeviceDataPanel", () => ({ DeviceDataPanel: () => null }));
vi.mock("../../services/syncService", () => ({
  syncService: {
    getStatus: () => ({ state: "available_offline", pendingCount: 0, lastSyncTime: null }),
    subscribe: () => () => {},
    clearWorkspace: async (ownerId: string) => movieService.clearLocalData(ownerId),
  },
}));
vi.mock("../../services/movieService", () => ({
  movieService: {
    clearLocalData: vi.fn().mockResolvedValue(undefined),
  },
}));

describe("AccountSheet", () => {
  const mockUser = {
    email: "user@example.com",
    display_name: "Cinephile User",
  };

  it("renders user details and sync section when open", () => {
    render(
      <AccountSheet
        isOpen={true}
        onClose={() => {}}
        user={mockUser}
        ownerId="local_owner"
      />
    );

    expect(screen.getByText("Cinephile User")).not.toBeNull();
    expect(screen.getByText("user@example.com")).not.toBeNull();
    expect(screen.getByText("Data Sync Status")).not.toBeNull();
    expect(screen.getByRole("button", { name: /sync now/i })).not.toBeNull();
  });

  it("opens clear confirmation modal and calls movieService.clearLocalData on confirm", async () => {
    const handleDataCleared = vi.fn();
    render(
      <AccountSheet
        isOpen={true}
        onClose={() => {}}
        user={mockUser}
        ownerId="local_owner"
        onDataCleared={handleDataCleared}
      />
    );

    const clearTrigger = screen.getByRole("button", { name: /clear local data\.\.\./i });
    fireEvent.click(clearTrigger);

    expect(screen.getByText("⚠️ Clear Local Data?")).not.toBeNull();

    const confirmBtn = screen.getByRole("button", { name: "Clear Data" });
    expect(confirmBtn.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(confirmBtn);

    await waitFor(() => expect(movieService.clearLocalData).toHaveBeenCalledWith("local_owner"));
  });
});
