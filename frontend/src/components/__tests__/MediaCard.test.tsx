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
  vote_average: 8.8,
};

describe("MediaCard", () => {
  it("renders movie title, metadata, and normalized availability status", () => {
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

    expect(screen.getByRole("heading", { name: "Inception" })).not.toBeNull();
    expect(screen.getByText("★ 8.8")).not.toBeNull();
    expect(screen.getByText("Movie · 2010")).not.toBeNull();
    expect(screen.getByText("Released")).not.toBeNull();
  });

  it("renders TV series season availability status", () => {
    const tvShow: MediaItem = {
      id: 456,
      media_type: "tv",
      title: "Severance",
      release_date: "2022-02-18",
      number_of_seasons: 4,
      number_of_episodes: 34,
      next_season: {
        name: "Season 4",
        season_number: 4,
        air_date: "2026-09-18",
      },
    };

    render(
      <MediaCard
        item={tvShow}
        onOpen={() => {}}
      />
    );

    expect(screen.getByRole("heading", { name: "Severance" })).not.toBeNull();
    expect(screen.getByText("Season 4 premieres Sep 18")).not.toBeNull();
  });

  it("calls onOpen when View details primary button is clicked", () => {
    const handleOpen = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={handleOpen}
      />
    );

    const viewButton = screen.getByRole("button", { name: "View details for Inception" });
    fireEvent.click(viewButton);
    expect(handleOpen).toHaveBeenCalledWith(mockMovie);
  });

  it("opens overflow menu and triggers onRemove when Remove option is clicked", () => {
    const handleRemove = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={() => {}}
        onRemove={handleRemove}
        isOnQueue={true}
      />
    );

    const optionsButton = screen.getByRole("button", { name: "Options for Inception" });
    fireEvent.click(optionsButton);

    const removeOption = screen.getByRole("menuitem", { name: "Remove" });
    fireEvent.click(removeOption);
    expect(handleRemove).toHaveBeenCalledWith(mockMovie);
  });

  it("opens overflow menu and triggers onAdd when + Add to Queue option is clicked", () => {
    const handleAdd = vi.fn();
    render(
      <MediaCard
        item={mockMovie}
        onOpen={() => {}}
        onAdd={handleAdd}
        isOnQueue={false}
        isOnWatchlist={false}
      />
    );

    const optionsButton = screen.getByRole("button", { name: "Options for Inception" });
    fireEvent.click(optionsButton);

    const addOption = screen.getByRole("menuitem", { name: "+ Add to Queue" });
    fireEvent.click(addOption);
    expect(handleAdd).toHaveBeenCalledWith(mockMovie);
  });
});
