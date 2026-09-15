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

  it("formatSummaryLines returns headline and supportingText for updates", () => {
    const result = formatSummaryLines("Unused text", [
      {
        title: "The Odyssey",
        type: "memory_recall",
        message: "You asked about The Odyssey on 2026-07-22.",
      },
    ]);

    expect(result.headline).toBe("1 new update since last visit");
    expect(result.supportingText).toBe("The Odyssey is now available.");
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

  it("collapsed state displays plain TODAY eyebrow, headline, and primary button", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText("TODAY")).toBeInTheDocument();
    expect(screen.getByText("1 new update since last visit")).toBeInTheDocument();
    expect(screen.getByText("The Odyssey opened in theaters on July 17.")).toBeInTheDocument();
  });

  it("chevron button toggles expanded state with aria-expanded attribute", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    const chevronBtn = await screen.findByRole("button", { name: /Expand details/i });
    expect(chevronBtn).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(chevronBtn);

    const collapseBtn = await screen.findByRole("button", { name: /Collapse details/i });
    expect(collapseBtn).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("briefing-expanded-content")).toBeInTheDocument();
  });

  it("does not render when updates_count is 0", async () => {
    vi.mocked(api.agentBriefing).mockResolvedValueOnce({
      enabled: true,
      briefing: "No new releases on your watchlist today or since your last visit.",
      updates_count: 0,
      updates: [],
      personality_preset: "cinephile",
    } as any);

    const { container } = render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(1);
    });

    expect(container.querySelector(".concise-daily-update")).toBeNull();
    expect(screen.queryByText("TODAY")).not.toBeInTheDocument();
  });

  it("does not auto-speak briefing audio on mount", async () => {
    const speakMock = vi.fn();
    window.speechSynthesis = {
      speak: speakMock,
      cancel: vi.fn(),
      paused: false,
      pending: false,
      speaking: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
      getVoices: vi.fn().mockReturnValue([]),
      pause: vi.fn(),
      resume: vi.fn(),
    } as any;

    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(1);
    });

    // Advance time slightly to ensure no delayed auto-speech triggers
    await new Promise((r) => setTimeout(r, 1500));
    expect(speakMock).not.toHaveBeenCalled();
  });
});
