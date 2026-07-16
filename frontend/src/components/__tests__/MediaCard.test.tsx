
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MediaCard } from "../MediaCard";
import type { MediaItem } from "../../types";

const mockMovie: MediaItem = {
  id: 123,
  media_type: "movie",
  title: "Inception",
  overview: "A thief who steals corporate secrets through the use of dream-sharing technology.",
  poster_url: "https://image.tmdb.org/t/p/w342/poster.jpg",
  release_date: "2010-07-16",
  days_label: "Released 16 years ago",
  vote_average: 8.8,
};

describe("MediaCard", () => {
  it("renders movie details correctly", () => {
    render(
      <MediaCard
        item={mockMovie}
        onOpen={() => {}}
        onAdd={() => {}}
        onRemove={() => {}}
        isOnWatchlist={false}
        isOwned={false}
      />
    );

    expect(screen.getByText("Inception")).not.toBeNull();
    expect(screen.getByText("★ 8.8")).not.toBeNull();
    expect(screen.getByText("Released 16 years ago")).not.toBeNull();
    expect(screen.getByText("2010-07-16")).not.toBeNull();
  });

  it("calls onOpen when clicked", () => {
    const handleOpen = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={handleOpen}
        isOnWatchlist={false}
      />
    );

    const cardButton = screen.getByRole("button", { name: /open inception/i });
    fireEvent.click(cardButton);
    expect(handleOpen).toHaveBeenCalledWith(mockMovie);
  });

  it("shows + Queue button when not on watchlist and triggers onAdd", () => {
    const handleAdd = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={() => {}}
        onAdd={handleAdd}
        isOnWatchlist={false}
        isOwned={false}
      />
    );

    const addButton = screen.getByRole("button", { name: /\+ queue/i });
    fireEvent.click(addButton);
    expect(handleAdd).toHaveBeenCalledWith(mockMovie);
  });

  it("shows Remove button when on watchlist and triggers onRemove", () => {
    const handleRemove = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={() => {}}
        onRemove={handleRemove}
        isOnWatchlist={true}
        isOwned={false}
      />
    );

    const removeButton = screen.getByRole("button", { name: /remove/i });
    fireEvent.click(removeButton);
    expect(handleRemove).toHaveBeenCalledWith(mockMovie);
  });
});
