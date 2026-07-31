import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MobileBottomNav } from "../MobileBottomNav";

describe("MobileBottomNav", () => {
  it("renders 5 mobile nav items with correct active tab", () => {
    render(<MobileBottomNav activeTab="watchlist" onChangeTab={() => {}} />);

    expect(screen.getByRole("tab", { name: /queue/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /monitoring/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /library/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /ratings/i })).not.toBeNull();
    expect(screen.getByRole("tab", { name: /search/i })).not.toBeNull();

    const queueTab = screen.getByRole("tab", { name: /queue/i });
    expect(queueTab.getAttribute("aria-selected")).toBe("true");
    expect(queueTab.getAttribute("aria-current")).toBe("page");
  });

  it("calls onChangeTab when a tab is clicked", () => {
    const handleChange = vi.fn();
    render(<MobileBottomNav activeTab="watchlist" onChangeTab={handleChange} />);

    const monitoringTab = screen.getByRole("tab", { name: /monitoring/i });
    fireEvent.click(monitoringTab);
    expect(handleChange).toHaveBeenCalledWith("following");
  });
});
