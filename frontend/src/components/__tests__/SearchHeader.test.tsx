import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchHeader } from "../SearchHeader";

describe("SearchHeader", () => {
  const mockUser = {
    email: "test@example.com",
    display_name: "Test User",
  };

  it("renders compact brand wordmark and user avatar", () => {
    render(
      <SearchHeader
        query=""
        setQuery={() => {}}
        onSubmit={() => {}}
        user={mockUser}
      />
    );

    expect(screen.getByText("CineQueue")).not.toBeNull();
    expect(screen.getByRole("button", { name: /open account menu for test user/i })).not.toBeNull();
  });

  it("handles search input change and clear button", () => {
    const handleSetQuery = vi.fn();
    render(
      <SearchHeader
        query="Inception"
        setQuery={handleSetQuery}
        onSubmit={() => {}}
        user={mockUser}
      />
    );

    const clearBtn = screen.getByRole("button", { name: "Clear search" });
    fireEvent.click(clearBtn);
    expect(handleSetQuery).toHaveBeenCalledWith("");
  });

  it("opens AccountSheet when avatar button is clicked", () => {
    render(
      <SearchHeader
        query=""
        setQuery={() => {}}
        onSubmit={() => {}}
        user={mockUser}
      />
    );

    const avatarBtn = screen.getByRole("button", { name: /open account menu for test user/i });
    fireEvent.click(avatarBtn);

    expect(screen.getByRole("dialog")).not.toBeNull();
    expect(screen.getByText("Test User")).not.toBeNull();
    expect(screen.getByText("test@example.com")).not.toBeNull();
  });
});
