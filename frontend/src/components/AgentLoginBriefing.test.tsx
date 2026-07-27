import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import {
  AgentLoginBriefing,
  cleanTextForSpeech,
  formatSummaryLines,
} from "./AgentLoginBriefing";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    agentBriefing: vi.fn(),
  },
}));

describe("AgentLoginBriefing Text Cleaning & Summary Utilities", () => {
  it("cleanTextForSpeech strips system notes, markdown, and internal jargon", () => {
    const raw =
      "[System Note: test] **MEMORY RECALL:** You asked about The Odyssey. • Random movie fact: trivia content.";
    const cleaned = cleanTextForSpeech(raw);
    expect(cleaned).not.toContain("[System Note:");
    expect(cleaned).not.toContain("MEMORY RECALL:");
    expect(cleaned).not.toContain("Random movie fact:");
    expect(cleaned).toContain("You asked about The Odyssey.");
  });

  it("formatSummaryLines returns clean complete summary lines without jargon", () => {
    const result = formatSummaryLines("Unused text", [
      {
        title: "The Odyssey",
        type: "memory_recall",
        message: "You asked about The Odyssey on 2026-07-22.",
      },
      {
        title: "Dune Part Two",
        type: "price_drop",
        message: "Price dropped.",
      },
    ]);

    expect(result.line1).toBe("The Odyssey is now available.");
    expect(result.line2).toBe("There is 1 additional monitored-title update.");
  });

  it("formatSummaryLines correctly handles plural additional updates count", () => {
    const result = formatSummaryLines("Unused text", [
      { title: "Item 1", type: "update", message: "Item 1 is available." },
      { title: "Item 2", type: "update", message: "Item 2 update." },
      { title: "Item 3", type: "update", message: "Item 3 update." },
    ]);

    expect(result.line1).toBe("Item 1 is available.");
    expect(result.line2).toBe("There are 2 additional monitored-title updates.");
  });
});

describe("AgentLoginBriefing Frontend Behavior & Accessibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(api.agentBriefing).mockResolvedValue({
      enabled: true,
      briefing: "Welcome back! The Odyssey was released on July 17.",
      updates_count: 1,
      updates: [
        {
          title: "The Odyssey",
          type: "release",
          message: "The Odyssey opened in theaters on July 17.",
        },
      ],
      personality_preset: "cinephile",
    } as any);
  });

  it("collapsed state displays complete summary text and correct header update count", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText("1 new update")).toBeInTheDocument();
    expect(screen.getByText("The Odyssey opened in theaters on July 17.")).toBeInTheDocument();
    expect(screen.queryByText("MEMORY RECALL:")).not.toBeInTheDocument();
  });

  it("toggle details button switches between Show details and Hide details with correct aria-expanded", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    const toggleBtn = await screen.findByRole("button", { name: /Show details/i });
    expect(toggleBtn).toHaveAttribute("aria-expanded", "false");
    expect(toggleBtn).toHaveAttribute("aria-controls", "briefing-details-content");

    fireEvent.click(toggleBtn);

    const expandedToggleBtn = await screen.findByRole("button", { name: /Hide details/i });
    expect(expandedToggleBtn).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("briefing-details-content")).toBeInTheDocument();
  });

  it("standalone X button is absent and replaced by 3-dot overflow menu", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    expect(screen.queryByLabelText("Dismiss briefing card")).not.toBeInTheDocument();

    const menuTrigger = screen.getByRole("button", { name: /Briefing options/i });
    expect(menuTrigger).toBeInTheDocument();

    fireEvent.click(menuTrigger);

    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Refresh briefing/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Dismiss for today/i })).toBeInTheDocument();
  });

  it("refresh inside 3-dot overflow menu explicitly calls api.agentBriefing with forceRefresh=true", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    const menuTrigger = screen.getByRole("button", { name: /Briefing options/i });
    fireEvent.click(menuTrigger);

    const refreshMenuItem = screen.getByRole("menuitem", { name: /Refresh briefing/i });
    fireEvent.click(refreshMenuItem);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(2);
      expect(api.agentBriefing).toHaveBeenLastCalledWith(expect.any(String), true);
    });
  });

  it("single update count presentation: primary button is simply 'View updates'", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    const viewUpdatesBtn = screen.getByRole("button", { name: /View updates/i });
    expect(viewUpdatesBtn).toBeInTheDocument();
    expect(viewUpdatesBtn.textContent).toBe("🔍 View updates");
    expect(screen.queryByText(/View updates \(1\)/i)).not.toBeInTheDocument();
  });

  it("pressing Escape key closes 3-dot menu and returns focus to menu trigger button", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    const menuTrigger = screen.getByRole("button", { name: /Briefing options/i });
    fireEvent.click(menuTrigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(menuTrigger);
  });
});
