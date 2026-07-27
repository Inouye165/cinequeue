import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Tabs, TabType } from "../Tabs";

const MOCK_TABS: { id: TabType; label: string }[] = [
  { id: "watchlist", label: "My Queue" },
  { id: "following", label: "Monitoring" },
  { id: "library", label: "My Library" },
  { id: "rated", label: "My Ratings" },
  { id: "upcoming", label: "Upcoming" },
  { id: "theatres", label: "In Theatres" },
];

describe("Tabs Navigation Component", () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  it("renders all tab labels completely without truncation or ellipsis", () => {
    render(<Tabs tabsList={MOCK_TABS} activeTab="watchlist" onChangeTab={() => {}} />);

    const myRatingsTab = screen.getByRole("tab", { name: "My Ratings" });
    expect(myRatingsTab).toBeInTheDocument();
    expect(myRatingsTab.textContent).toBe("My Ratings");
    expect(screen.queryByText(/My Rati…/i)).not.toBeInTheDocument();
  });

  it("sets correct aria-selected and tabIndex attributes on active vs inactive tabs", () => {
    render(<Tabs tabsList={MOCK_TABS} activeTab="rated" onChangeTab={() => {}} />);

    const activeTab = screen.getByRole("tab", { name: "My Ratings" });
    expect(activeTab).toHaveAttribute("aria-selected", "true");
    expect(activeTab).toHaveAttribute("tabIndex", "0");

    const inactiveTab = screen.getByRole("tab", { name: "My Queue" });
    expect(inactiveTab).toHaveAttribute("aria-selected", "false");
    expect(inactiveTab).toHaveAttribute("tabIndex", "-1");
  });

  it("automatically calls scrollIntoView on active tab change", () => {
    render(<Tabs tabsList={MOCK_TABS} activeTab="rated" onChangeTab={() => {}} />);

    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("supports keyboard arrow navigation between tabs", () => {
    const handleChange = vi.fn();
    render(<Tabs tabsList={MOCK_TABS} activeTab="watchlist" onChangeTab={handleChange} />);

    const firstTab = screen.getByRole("tab", { name: "My Queue" });
    fireEvent.keyDown(firstTab, { key: "ArrowRight" });

    expect(handleChange).toHaveBeenCalledWith("following");
  });
});
