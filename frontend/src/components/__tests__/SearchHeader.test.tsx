import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchHeader } from "../SearchHeader";
import type { SearchFilterState } from "../../types";

describe("SearchHeader", () => {
  const mockUser = {
    email: "test@example.com",
    display_name: "Test User",
  };

  const defaultFilters: SearchFilterState = {
    query: "",
    actors: [],
    director: "",
    yearType: "any",
    mediaType: "all",
  };

  it("renders compact brand wordmark and user avatar", () => {
    render(
      <SearchHeader
        query=""
        setQuery={() => {}}
        onSubmit={() => {}}
        user={mockUser}
        filters={defaultFilters}
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
        filters={defaultFilters}
      />
    );

    const clearBtn = screen.getByRole("button", { name: "Clear search" });
    fireEvent.click(clearBtn);
    expect(handleSetQuery).toHaveBeenCalledWith("");
  });

  it("renders active filter pills and calls onUpdateFilters on removal", () => {
    const handleUpdateFilters = vi.fn();
    const activeFilters: SearchFilterState = {
      query: "Inception",
      actors: ["Leonardo DiCaprio", "Joseph Gordon-Levitt"],
      director: "Christopher Nolan",
      yearType: "exact",
      year: 2010,
      mediaType: "movie",
    };

    render(
      <SearchHeader
        query="Inception"
        setQuery={() => {}}
        onSubmit={() => {}}
        filters={activeFilters}
        onUpdateFilters={handleUpdateFilters}
        user={mockUser}
      />
    );

    expect(screen.getByText(/Leonardo DiCaprio/i)).not.toBeNull();
    expect(screen.getByText(/Joseph Gordon-Levitt/i)).not.toBeNull();
    expect(screen.getByText(/Christopher Nolan/i)).not.toBeNull();
    expect(screen.getByText(/2010/i)).not.toBeNull();

    // Click remove on an actor pill
    const removeActorBtn = screen.getByRole("button", { name: /remove actor filter leonardo dicaprio/i });
    fireEvent.click(removeActorBtn);
    expect(handleUpdateFilters).toHaveBeenCalledWith(
      expect.objectContaining({
        actors: ["Joseph Gordon-Levitt"],
      })
    );
  });

  it("opens filters drawer when filter toggle button is clicked", () => {
    render(
      <SearchHeader
        query=""
        setQuery={() => {}}
        onSubmit={() => {}}
        filters={defaultFilters}
        onUpdateFilters={() => {}}
        user={mockUser}
      />
    );

    const filterToggleBtn = screen.getByRole("button", { name: /search filters/i });
    fireEvent.click(filterToggleBtn);

    expect(screen.getByText("Advanced Search Filters")).not.toBeNull();
  });
});
