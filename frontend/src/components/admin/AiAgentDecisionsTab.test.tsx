import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { AiAgentDecisionsTab } from "./AiAgentDecisionsTab";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: {
    adminAgentDecisionLogs: vi.fn(),
    adminAgentDecisionConfig: vi.fn(),
    adminAgentPromptVersions: vi.fn(),
  },
}));

describe("AiAgentDecisionsTab Diagnostics Telemetry UI", () => {
  const sampleLogs = [
    {
      log_id: "log_123",
      timestamp: "2026-07-24T20:00:00Z",
      user_id: "user_1",
      event_type: "startup_briefing_run_completed",
      result_source: "persistent_daily_cache",
      served_from: "persistent_daily_cache",
      content_origin: "gemini_primary",
      daily_cache_result: "hit",
      configured_user_timezone: "America/Los_Angeles",
      resolved_user_timezone: "America/Los_Angeles",
      timezone_resolution_source: "user_setting",
      resolved_local_date: "2026-07-24",
      gemini_called: false,
      fallback_used: false,
      is_legacy: false,
      selection_summary: "Served: persistent_daily_cache | Origin: gemini_primary",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.adminAgentDecisionLogs).mockResolvedValue({
      logs: sampleLogs,
      total: 1,
    } as any);
    vi.mocked(api.adminAgentDecisionConfig).mockResolvedValue({} as any);
    vi.mocked(api.adminAgentPromptVersions).mockResolvedValue({ versions: [], active_version: null } as any);
  });

  it("renders Served From and Content Origin badges in the log row", async () => {
    render(<AiAgentDecisionsTab />);

    await waitFor(() => {
      expect(api.adminAgentDecisionLogs).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/Served: persistent_daily_cache/i)).toBeInTheDocument();
    expect(screen.getByText(/Origin: gemini_primary/i)).toBeInTheDocument();
  });

  it("opens log drawer and displays Daily Cache Result, Resolved Timezone, and Local Date", async () => {
    render(<AiAgentDecisionsTab />);

    await waitFor(() => expect(api.adminAgentDecisionLogs).toHaveBeenCalledTimes(1));

    const inspectBtn = await screen.findByText(/Inspect Log/i);
    fireEvent.click(inspectBtn);

    await waitFor(() => {
      expect(screen.getByText(/Daily Cache Result/i)).toBeInTheDocument();
    });

    expect(screen.getByText("Daily Cache Result:")).toBeInTheDocument();
    expect(screen.getByText("America/Los_Angeles")).toBeInTheDocument();
    expect(screen.getByText("2026-07-24")).toBeInTheDocument();
  });
});
