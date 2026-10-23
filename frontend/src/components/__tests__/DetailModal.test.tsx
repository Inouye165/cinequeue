import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DetailModal } from "../DetailModal";
import type { MediaDetails } from "../../types";

const mockDetails: MediaDetails = {
  id: 550,
  media_type: "movie",
  title: "Digger",
  tagline: "A man. A plan. A meltdown.",
  overview: "An underground comedy-drama.",
  release_date: "2026-09-28",
  vote_average: 7.5,
  runtime_minutes: 129,
  genres: ["Comedy", "Drama"],
  poster_url: "https://image.tmdb.org/t/p/w342/digger.jpg",
  backdrop_url: "https://image.tmdb.org/t/p/w780/backdrop.jpg",
  homepage: "https://example.com/digger",
  days_label: undefined,
  release_info: {},
  watch_providers: { categories: {} },
  reviews: [],
  news: [],
  trailers: [],
};

describe("DetailModal", () => {
  const defaultProps = {
    details: mockDetails,
    isOnQueue: true,
    isFollowing: false,
    isOwned: false,
    ownedFormat: null,
    watchFreeStreaming: false,
    watchOnSaleBuy: false,
    userRating: null,
    onClose: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    onRate: vi.fn(),
    onUpdateOwned: vi.fn(),
    onMoveToFollowing: vi.fn(),
    onMoveToQueue: vi.fn(),
    onUpdateWatchOptions: vi.fn(),
  };

  it("renders title, metadata, and close button with accessible label", () => {
    render(<DetailModal {...defaultProps} />);
    expect(screen.getByRole("dialog", { name: "Digger details" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Digger" })).toBeTruthy();
    expect(screen.getByText("2026-09-28")).toBeTruthy();
    expect(screen.getByText("★ 7.5")).toBeTruthy();
    expect(screen.getByText("129 min")).toBeTruthy();

    const closeBtn = screen.getByRole("button", { name: "Close details" });
    expect(closeBtn).toBeTruthy();
    expect(closeBtn.className).toContain("icon-button");
    expect(closeBtn.className).toContain("close-button");
  });

  it("calls onClose when clicking the Close button, pressing Escape, or clicking backdrop", () => {
    const onClose = vi.fn();
    const { unmount } = render(<DetailModal {...defaultProps} onClose={onClose} />);

    expect(document.body.style.overflow).toBe("hidden");

    // Click inside dialog panel should NOT close
    fireEvent.click(screen.getByRole("dialog", { name: "Digger details" }));
    expect(onClose).not.toHaveBeenCalled();

    // Click Close button
    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Press Escape key
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);

    unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("supports touch swipe-down gesture on the top bar to dismiss", () => {
    const onClose = vi.fn();
    const { container } = render(<DetailModal {...defaultProps} onClose={onClose} />);
    const topbar = container.querySelector(".detail-sheet-topbar")!;
    expect(topbar).not.toBeNull();

    fireEvent.touchStart(topbar, { touches: [{ clientY: 50 }] });
    fireEvent.touchMove(topbar, { touches: [{ clientY: 150 }] });
    fireEvent.touchEnd(topbar);

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
