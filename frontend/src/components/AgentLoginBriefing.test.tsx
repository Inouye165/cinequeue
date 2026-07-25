import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { AgentLoginBriefing } from "./AgentLoginBriefing";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    agentBriefing: vi.fn(),
  },
}));

describe("AgentLoginBriefing Frontend Behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(api.agentBriefing).mockResolvedValue({
      enabled: true,
      briefing: "Welcome back! The Odyssey was released on July 17.",
      updates_count: 1,
      updates: [],
      personality_preset: "cinephile",
    } as any);
  });

  it("normal mount calls api.agentBriefing with forceRefresh=false", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(1);
      expect(api.agentBriefing).toHaveBeenCalledWith(expect.any(String), false);
    });

    expect(await screen.findByText(/Welcome back! The Odyssey was released on July 17/i)).toBeInTheDocument();
  });

  it("manual refresh button click explicitly calls api.agentBriefing with forceRefresh=true", async () => {
    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    const refreshBtn = await screen.findByTitle(/Manually refresh today's briefing/i);
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(api.agentBriefing).toHaveBeenCalledTimes(2);
      expect(api.agentBriefing).toHaveBeenLastCalledWith(expect.any(String), true);
    });
  });

  it("re-render does not cause duplicate active requests", async () => {
    const { rerender } = render(<AgentLoginBriefing onOpenChat={() => {}} />);

    await waitFor(() => expect(api.agentBriefing).toHaveBeenCalledTimes(1));

    rerender(<AgentLoginBriefing onOpenChat={() => {}} />);

    expect(api.agentBriefing).toHaveBeenCalledTimes(1);
  });

  it("clicking updates count badge opens modal dialog displaying updates list", async () => {
    vi.mocked(api.agentBriefing).mockResolvedValue({
      enabled: true,
      briefing: "Welcome back! The Odyssey is available.",
      updates_count: 1,
      updates: [
        {
          title: "The Odyssey",
          type: "memory_recall",
          message: "You asked about The Odyssey on 2026-07-22.",
        },
      ],
      personality_preset: "cinephile",
    } as any);

    render(<AgentLoginBriefing onOpenChat={() => {}} />);

    const badgeBtn = await screen.findByRole("button", { name: /1 update/i });
    expect(badgeBtn).toBeInTheDocument();

    fireEvent.click(badgeBtn);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Updates & Changes Since Last Login/i)).toBeInTheDocument();
    expect(screen.getByText("The Odyssey")).toBeInTheDocument();
    expect(screen.getByText("You asked about The Odyssey on 2026-07-22.")).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /Close modal/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /1 update/i })).not.toBeInTheDocument();
  });
});
