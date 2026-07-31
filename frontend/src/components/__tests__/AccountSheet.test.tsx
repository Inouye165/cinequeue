import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AccountSheet } from "../AccountSheet";
import { movieService } from "../../services/movieService";

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
    fireEvent.click(confirmBtn);

    expect(movieService.clearLocalData).toHaveBeenCalledWith("local_owner");
  });
});
