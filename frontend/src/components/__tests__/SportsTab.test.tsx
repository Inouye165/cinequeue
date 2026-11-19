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

  it("renders movie-format game cards with both team logos, current records, and prominent game time between teams", () => {
    const prefs: SportsPreferences = {
      streaming_services: ["peacock"],
      tracked_teams: ["nfl_kc"],
      show_in_queue: true,
      setup_completed: true,
    };

    const { container } = render(
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

    const kickoffPills = container.querySelectorAll(".sports-poster-kickoff-time");
    expect(kickoffPills.length).toBe(2);
    expect(kickoffPills[0].textContent).toMatch(/\d{1,2}:\d{2}/);
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
      { ...MOCK_GAMES[0], id: "fri_game", start_time: "2026-10-23T12:00:00" },
      { ...MOCK_GAMES[0], id: "sat_game", start_time: "2026-10-24T12:00:00" },
      { ...MOCK_GAMES[0], id: "sun_game", start_time: "2026-10-25T12:00:00" },
      { ...MOCK_GAMES[0], id: "mon_game", start_time: "2026-10-26T12:00:00" },
    ];

    // On Friday Oct 23, 2026: keeps Fri, Sat, Sun (excludes Mon)
    const fridayResult = filterGamesForActiveWindow(sampleGames, new Date("2026-10-23T10:00:00"));
    expect(fridayResult.map((g) => g.id)).toEqual(["fri_game", "sat_game", "sun_game"]);

    // On Sunday Oct 25, 2026: keeps only Sunday's game
    const sundayResult = filterGamesForActiveWindow(sampleGames, new Date("2026-10-25T10:00:00"));
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

  it("opens full-screen scoreboard modal when a game card is clicked and supports live score refresh", async () => {
    const liveGame: SportsGame = {
      ...MOCK_GAMES[0],
      id: "nba_live_1",
      status: "live",
      status_detail: "Q3 4:12",
      is_live: true,
      is_completed: false,
      last_play: "LeBron James makes 3-pt jump shot",
      home_team: { ...MOCK_GAMES[0].home_team, score: "82", linescores: ["28", "26", "28"] },
      away_team: { ...MOCK_GAMES[0].away_team, score: "79", linescores: ["24", "30", "25"] },
    };

    const handleRefresh = vi.fn().mockResolvedValue(undefined);
    const prefs: SportsPreferences = {
      streaming_services: ["youtube_tv"],
      tracked_teams: ["nba_lal"],
      show_in_queue: true,
      setup_completed: true,
    };

    render(
      <SportsTab
        catalog={DEFAULT_CATALOG}
        games={[liveGame]}
        preferences={prefs}
        loading={false}
        onSavePreferences={vi.fn()}
        onRefreshSchedule={handleRefresh}
      />
    );

    const card = screen.getByRole("button", { name: /NFL: San Francisco 49ers at Kansas City Chiefs/i });
    fireEvent.click(card);

    const dialog = screen.getByRole("dialog", { name: /San Francisco 49ers at Kansas City Chiefs scoreboard/i });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByTestId("away-score")).toHaveTextContent("79");
    expect(screen.getByTestId("home-score")).toHaveTextContent("82");
    expect(screen.getByText("LeBron James makes 3-pt jump shot")).toBeInTheDocument();
    expect(screen.getByText("Score by Period")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Refresh live score/i }));
    expect(handleRefresh).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Close game scoreboard/i }));
    expect(screen.queryByRole("dialog", { name: /scoreboard/i })).toBeNull();
  });
});
