import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { SportsTab } from "../SportsTab";
import { DEFAULT_CATALOG, enrichGameStreamingServices, filterGamesForActiveWindow } from "../../services/sportsService";
import type { SportsGame, SportsPreferences } from "../../types";

const MOCK_GAMES: SportsGame[] = [
  {
    id: "nfl_1",
    league: "NFL",
    title: "San Francisco 49ers at Kansas City Chiefs",
    short_title: "SF @ KC",
    start_time: "2026-10-25T20:20:00Z",
    status: "scheduled",
    status_detail: "Sun, Oct 25 • 8:20 PM",
    is_live: false,
    is_completed: false,
    venue: "Arrowhead Stadium",
    home_team: {
      id: "nfl_kc",
      league: "NFL",
      abbr: "KC",
      name: "Kansas City Chiefs",
      short_name: "Chiefs",
      logo: "",
      record: "5-1",
    },
    away_team: {
      id: "nfl_sf",
      league: "NFL",
      abbr: "SF",
      name: "San Francisco 49ers",
      short_name: "49ers",
      logo: "",
      record: "4-3",
    },
    broadcasts: ["NBC", "Peacock"],
    streaming_service_ids: ["peacock", "youtube_tv"],
    streaming_services: [
      {
        id: "peacock",
        name: "Peacock",
        short_name: "Peacock",
        color: "#000000",
        badge_bg: "#1e293b",
        description: "NBC Sunday Night Football",
      },
    ],
  },
  {
    id: "nba_1",
    league: "NBA",
    title: "Boston Celtics at Los Angeles Lakers",
    short_title: "BOS @ LAL",
    start_time: "2026-10-26T02:00:00Z",
    status: "scheduled",
    status_detail: "Sun, Oct 25 • 10:00 PM",
    is_live: false,
    is_completed: false,
    venue: "Crypto.com Arena",
    home_team: {
      id: "nba_lal",
      league: "NBA",
      abbr: "LAL",
      name: "Los Angeles Lakers",
      short_name: "Lakers",
      logo: "",
      record: "2-0",
    },
    away_team: {
      id: "nba_bos",
      league: "NBA",
      abbr: "BOS",
      name: "Boston Celtics",
      short_name: "Celtics",
      logo: "",
      record: "2-0",
    },
    broadcasts: ["ESPN", "ABC"],
    streaming_service_ids: ["espn_plus"],
    streaming_services: [
      {
        id: "espn_plus",
        name: "ESPN+ / ESPN App",
        short_name: "ESPN+",
        color: "#cc0000",
        badge_bg: "#b91c1c",
        description: "NBA on ESPN",
      },
    ],
  },
];

describe("SportsTab Component", () => {
  it("prompts user to set up streaming services and teams on first visit (setup_completed = false)", () => {
    const prefs: SportsPreferences = {
      streaming_services: [],
      tracked_teams: [],
      show_in_queue: true,
      setup_completed: false,
    };

    render(
      <SportsTab
        catalog={DEFAULT_CATALOG}
        games={MOCK_GAMES}
        preferences={prefs}
        loading={false}
        onSavePreferences={vi.fn()}
        onRefreshSchedule={vi.fn()}
      />
    );

    expect(
      screen.getByRole("dialog", { name: /Set Up Your Sports & Streaming Services/i })
    ).toBeInTheDocument();
  });

  it("renders movie-format game cards with both team logos and current records", () => {
    const prefs: SportsPreferences = {
      streaming_services: ["peacock"],
      tracked_teams: ["nfl_kc"],
      show_in_queue: true,
      setup_completed: true,
    };

    render(
      <SportsTab
        catalog={DEFAULT_CATALOG}
        games={MOCK_GAMES}
        preferences={prefs}
        loading={false}
        onSavePreferences={vi.fn()}
        onRefreshSchedule={vi.fn()}
      />
    );

    expect(screen.getByAltText("San Francisco 49ers logo")).toBeInTheDocument();
    expect(screen.getByAltText("Kansas City Chiefs logo")).toBeInTheDocument();
    expect(screen.getByText("5-1")).toBeInTheDocument();
    expect(screen.getByText("4-3")).toBeInTheDocument();
  });

  it("allows adding and deleting streaming services and filtering by My Services vs All Services and My Teams vs All Teams", () => {
    const handleSave = vi.fn().mockResolvedValue(undefined);
    const prefs: SportsPreferences = {
      streaming_services: ["peacock"],
      tracked_teams: ["nba_lal"],
      show_in_queue: true,
      setup_completed: true,
    };

    render(
      <SportsTab
        catalog={DEFAULT_CATALOG}
        games={MOCK_GAMES}
        preferences={prefs}
        loading={false}
        onSavePreferences={handleSave}
        onRefreshSchedule={vi.fn()}
      />
    );

    // Initially both games are shown under "All Streaming Services" & "All Teams"
    expect(screen.getByText("Kansas City Chiefs")).toBeInTheDocument();
    expect(screen.getByText("Los Angeles Lakers")).toBeInTheDocument();

    // Filter by "My Services Only" (Peacock -> only Chiefs vs 49ers)
    fireEvent.click(screen.getByRole("button", { name: /My Services Only/i }));
    expect(screen.getByText("Kansas City Chiefs")).toBeInTheDocument();
    expect(screen.queryByText("Los Angeles Lakers")).not.toBeInTheDocument();

    // Switch back to "All Streaming Services" and filter by "My Teams Only" (Lakers -> only Celtics vs Lakers)
    fireEvent.click(screen.getByRole("button", { name: /All Streaming Services/i }));
    fireEvent.click(screen.getByRole("button", { name: /My Teams Only/i }));
    expect(screen.getByText("Los Angeles Lakers")).toBeInTheDocument();
    expect(screen.queryByText("Kansas City Chiefs")).not.toBeInTheDocument();

    // Toggle a streaming service chip (delete Peacock)
    const peacockChip = screen.getByRole("button", { name: /✓ Peacock/i });
    fireEvent.click(peacockChip);
    expect(handleSave).toHaveBeenCalledWith({
      streaming_services: [],
      setup_completed: true,
    });
  });

  it("filters games to Friday + Weekend when today is Friday, and current day only on other days", () => {
    const sampleGames: SportsGame[] = [
      { ...MOCK_GAMES[0], id: "fri_game", start_time: "2026-10-23T19:00:00-07:00" },
      { ...MOCK_GAMES[0], id: "sat_game", start_time: "2026-10-24T17:00:00-07:00" },
      { ...MOCK_GAMES[0], id: "sun_game", start_time: "2026-10-25T13:00:00-07:00" },
      { ...MOCK_GAMES[0], id: "mon_game", start_time: "2026-10-26T17:00:00-07:00" },
    ];

    // On Friday Oct 23, 2026: keeps Fri, Sat, Sun (excludes Mon)
    const fridayResult = filterGamesForActiveWindow(sampleGames, new Date("2026-10-23T12:00:00-07:00"));
    expect(fridayResult.map((g) => g.id)).toEqual(["fri_game", "sat_game", "sun_game"]);

    // On Sunday Oct 25, 2026: keeps only Sunday's game
    const sundayResult = filterGamesForActiveWindow(sampleGames, new Date("2026-10-25T10:00:00-07:00"));
    expect(sundayResult.map((g) => g.id)).toEqual(["sun_game"]);
  });

  it("maps FOX broadcasts to FOX One (fox_one) and allows adding FOX One to watch 49ers on FOX", () => {
    const foxNinersGame: SportsGame = enrichGameStreamingServices({
      ...MOCK_GAMES[0],
      id: "nfl_sf_atl",
      title: "San Francisco 49ers at Atlanta Falcons",
      short_title: "SF @ ATL",
      broadcasts: ["Fox"],
      streaming_service_ids: ["youtube_tv", "nfl_plus"],
      streaming_services: [],
    });

    expect(foxNinersGame.streaming_service_ids).toContain("fox_one");
    expect(foxNinersGame.streaming_services.some((s) => s.id === "fox_one")).toBe(true);

    const handleSave = vi.fn().mockResolvedValue(undefined);
    const prefs: SportsPreferences = {
      streaming_services: ["fox_one"],
      tracked_teams: ["nfl_sf"],
      show_in_queue: true,
      setup_completed: true,
    };

    render(
      <SportsTab
        catalog={DEFAULT_CATALOG}
        games={[foxNinersGame]}
        preferences={prefs}
        loading={false}
        onSavePreferences={handleSave}
        onRefreshSchedule={vi.fn()}
      />
    );

    expect(screen.getByText(/Watch on FOX One/i)).toBeInTheDocument();
  });
});
