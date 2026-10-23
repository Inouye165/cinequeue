import { db } from "../db/cinequeueDb";
import { api } from "../api";
import type { SportsCatalog, SportsGame, SportsPreferences, SportsTeam, StreamingServiceInfo } from "../types";

export const DEFAULT_STREAMING_SERVICES: StreamingServiceInfo[] = [
  { id: "peacock", name: "Peacock", short_name: "Peacock", color: "#000000", badge_bg: "#1e293b", description: "NBC Sunday Night Football, NBA on NBC/Peacock" },
  { id: "paramount_plus", name: "Paramount+", short_name: "Paramount+", color: "#0064ff", badge_bg: "#1d4ed8", description: "NFL on CBS live local & national games" },
  { id: "prime_video", name: "Prime Video", short_name: "Prime Video", color: "#00a8e1", badge_bg: "#0369a1", description: "Thursday Night Football & NBA on Prime" },
  { id: "espn_plus", name: "ESPN+ / ESPN App", short_name: "ESPN+", color: "#cc0000", badge_bg: "#b91c1c", description: "Monday Night Football, NBA on ESPN & ABC simulcasts" },
  { id: "max", name: "Max (B/R Sports)", short_name: "Max", color: "#002be7", badge_bg: "#3730a3", description: "NBA on TNT live games via B/R Sports" },
  { id: "youtube_tv", name: "YouTube TV / Live TV", short_name: "YouTube TV", color: "#ff0000", badge_bg: "#991b1b", description: "FOX, CBS, NBC, ABC, ESPN, TNT, NBA TV, NFL Network" },
  { id: "netflix", name: "Netflix", short_name: "Netflix", color: "#e50914", badge_bg: "#991b1b", description: "NFL Christmas Day & special live events" },
  { id: "nfl_plus", name: "NFL+ / Sunday Ticket", short_name: "NFL+", color: "#013369", badge_bg: "#1e3a8a", description: "Live local/primetime mobile games & out-of-market NFL" },
  { id: "nba_league_pass", name: "NBA League Pass", short_name: "League Pass", color: "#1d428a", badge_bg: "#1e40af", description: "Out-of-market live NBA games" },
];

export const DEFAULT_TEAMS: SportsTeam[] = [
  // NFL
  { id: "nfl_ari", league: "NFL", abbr: "ARI", name: "Arizona Cardinals", short_name: "Cardinals", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png" },
  { id: "nfl_atl", league: "NFL", abbr: "ATL", name: "Atlanta Falcons", short_name: "Falcons", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png" },
  { id: "nfl_bal", league: "NFL", abbr: "BAL", name: "Baltimore Ravens", short_name: "Ravens", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png" },
  { id: "nfl_buf", league: "NFL", abbr: "BUF", name: "Buffalo Bills", short_name: "Bills", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png" },
  { id: "nfl_car", league: "NFL", abbr: "CAR", name: "Carolina Panthers", short_name: "Panthers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/car.png" },
  { id: "nfl_chi", league: "NFL", abbr: "CHI", name: "Chicago Bears", short_name: "Bears", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png" },
  { id: "nfl_cin", league: "NFL", abbr: "CIN", name: "Cincinnati Bengals", short_name: "Bengals", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png" },
  { id: "nfl_cle", league: "NFL", abbr: "CLE", name: "Cleveland Browns", short_name: "Browns", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png" },
  { id: "nfl_dal", league: "NFL", abbr: "DAL", name: "Dallas Cowboys", short_name: "Cowboys", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png" },
  { id: "nfl_den", league: "NFL", abbr: "DEN", name: "Denver Broncos", short_name: "Broncos", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/den.png" },
  { id: "nfl_det", league: "NFL", abbr: "DET", name: "Detroit Lions", short_name: "Lions", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/det.png" },
  { id: "nfl_gb", league: "NFL", abbr: "GB", name: "Green Bay Packers", short_name: "Packers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png" },
  { id: "nfl_hou", league: "NFL", abbr: "HOU", name: "Houston Texans", short_name: "Texans", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png" },
  { id: "nfl_ind", league: "NFL", abbr: "IND", name: "Indianapolis Colts", short_name: "Colts", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png" },
  { id: "nfl_jax", league: "NFL", abbr: "JAX", name: "Jacksonville Jaguars", short_name: "Jaguars", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png" },
  { id: "nfl_kc", league: "NFL", abbr: "KC", name: "Kansas City Chiefs", short_name: "Chiefs", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png" },
  { id: "nfl_lv", league: "NFL", abbr: "LV", name: "Las Vegas Raiders", short_name: "Raiders", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png" },
  { id: "nfl_lac", league: "NFL", abbr: "LAC", name: "Los Angeles Chargers", short_name: "Chargers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png" },
  { id: "nfl_lar", league: "NFL", abbr: "LAR", name: "Los Angeles Rams", short_name: "Rams", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png" },
  { id: "nfl_mia", league: "NFL", abbr: "MIA", name: "Miami Dolphins", short_name: "Dolphins", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png" },
  { id: "nfl_min", league: "NFL", abbr: "MIN", name: "Minnesota Vikings", short_name: "Vikings", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/min.png" },
  { id: "nfl_ne", league: "NFL", abbr: "NE", name: "New England Patriots", short_name: "Patriots", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png" },
  { id: "nfl_no", league: "NFL", abbr: "NO", name: "New Orleans Saints", short_name: "Saints", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/no.png" },
  { id: "nfl_nyg", league: "NFL", abbr: "NYG", name: "New York Giants", short_name: "Giants", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png" },
  { id: "nfl_nyj", league: "NFL", abbr: "NYJ", name: "New York Jets", short_name: "Jets", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png" },
  { id: "nfl_phi", league: "NFL", abbr: "PHI", name: "Philadelphia Eagles", short_name: "Eagles", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png" },
  { id: "nfl_pit", league: "NFL", abbr: "PIT", name: "Pittsburgh Steelers", short_name: "Steelers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png" },
  { id: "nfl_sf", league: "NFL", abbr: "SF", name: "San Francisco 49ers", short_name: "49ers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png" },
  { id: "nfl_sea", league: "NFL", abbr: "SEA", name: "Seattle Seahawks", short_name: "Seahawks", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png" },
  { id: "nfl_tb", league: "NFL", abbr: "TB", name: "Tampa Bay Buccaneers", short_name: "Buccaneers", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png" },
  { id: "nfl_ten", league: "NFL", abbr: "TEN", name: "Tennessee Titans", short_name: "Titans", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png" },
  { id: "nfl_wsh", league: "NFL", abbr: "WSH", name: "Washington Commanders", short_name: "Commanders", logo: "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png" },

  // NBA
  { id: "nba_atl", league: "NBA", abbr: "ATL", name: "Atlanta Hawks", short_name: "Hawks", logo: "https://a.espncdn.com/i/teamlogos/nba/500/atl.png" },
  { id: "nba_bos", league: "NBA", abbr: "BOS", name: "Boston Celtics", short_name: "Celtics", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bos.png" },
  { id: "nba_bkn", league: "NBA", abbr: "BKN", name: "Brooklyn Nets", short_name: "Nets", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png" },
  { id: "nba_cha", league: "NBA", abbr: "CHA", name: "Charlotte Hornets", short_name: "Hornets", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cha.png" },
  { id: "nba_chi", league: "NBA", abbr: "CHI", name: "Chicago Bulls", short_name: "Bulls", logo: "https://a.espncdn.com/i/teamlogos/nba/500/chi.png" },
  { id: "nba_cle", league: "NBA", abbr: "CLE", name: "Cleveland Cavaliers", short_name: "Cavaliers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cle.png" },
  { id: "nba_dal", league: "NBA", abbr: "DAL", name: "Dallas Mavericks", short_name: "Mavericks", logo: "https://a.espncdn.com/i/teamlogos/nba/500/dal.png" },
  { id: "nba_den", league: "NBA", abbr: "DEN", name: "Denver Nuggets", short_name: "Nuggets", logo: "https://a.espncdn.com/i/teamlogos/nba/500/den.png" },
  { id: "nba_det", league: "NBA", abbr: "DET", name: "Detroit Pistons", short_name: "Pistons", logo: "https://a.espncdn.com/i/teamlogos/nba/500/det.png" },
  { id: "nba_gs", league: "NBA", abbr: "GS", name: "Golden State Warriors", short_name: "Warriors", logo: "https://a.espncdn.com/i/teamlogos/nba/500/gs.png" },
  { id: "nba_hou", league: "NBA", abbr: "HOU", name: "Houston Rockets", short_name: "Rockets", logo: "https://a.espncdn.com/i/teamlogos/nba/500/hou.png" },
  { id: "nba_ind", league: "NBA", abbr: "IND", name: "Indiana Pacers", short_name: "Pacers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/ind.png" },
  { id: "nba_lac", league: "NBA", abbr: "LAC", name: "LA Clippers", short_name: "Clippers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lac.png" },
  { id: "nba_lal", league: "NBA", abbr: "LAL", name: "Los Angeles Lakers", short_name: "Lakers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lal.png" },
  { id: "nba_mem", league: "NBA", abbr: "MEM", name: "Memphis Grizzlies", short_name: "Grizzlies", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mem.png" },
  { id: "nba_mia", league: "NBA", abbr: "MIA", name: "Miami Heat", short_name: "Heat", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mia.png" },
  { id: "nba_mil", league: "NBA", abbr: "MIL", name: "Milwaukee Bucks", short_name: "Bucks", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mil.png" },
  { id: "nba_min", league: "NBA", abbr: "MIN", name: "Minnesota Timberwolves", short_name: "Timberwolves", logo: "https://a.espncdn.com/i/teamlogos/nba/500/min.png" },
  { id: "nba_no", league: "NBA", abbr: "NO", name: "New Orleans Pelicans", short_name: "Pelicans", logo: "https://a.espncdn.com/i/teamlogos/nba/500/no.png" },
  { id: "nba_ny", league: "NBA", abbr: "NY", name: "New York Knicks", short_name: "Knicks", logo: "https://a.espncdn.com/i/teamlogos/nba/500/ny.png" },
  { id: "nba_okc", league: "NBA", abbr: "OKC", name: "Oklahoma City Thunder", short_name: "Thunder", logo: "https://a.espncdn.com/i/teamlogos/nba/500/okc.png" },
  { id: "nba_orl", league: "NBA", abbr: "ORL", name: "Orlando Magic", short_name: "Magic", logo: "https://a.espncdn.com/i/teamlogos/nba/500/orl.png" },
  { id: "nba_phi", league: "NBA", abbr: "PHI", name: "Philadelphia 76ers", short_name: "76ers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phi.png" },
  { id: "nba_phx", league: "NBA", abbr: "PHX", name: "Phoenix Suns", short_name: "Suns", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phx.png" },
  { id: "nba_por", league: "NBA", abbr: "POR", name: "Portland Trail Blazers", short_name: "Trail Blazers", logo: "https://a.espncdn.com/i/teamlogos/nba/500/por.png" },
  { id: "nba_sac", league: "NBA", abbr: "SAC", name: "Sacramento Kings", short_name: "Kings", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sac.png" },
  { id: "nba_sa", league: "NBA", abbr: "SA", name: "San Antonio Spurs", short_name: "Spurs", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sa.png" },
  { id: "nba_tor", league: "NBA", abbr: "TOR", name: "Toronto Raptors", short_name: "Raptors", logo: "https://a.espncdn.com/i/teamlogos/nba/500/tor.png" },
  { id: "nba_utah", league: "NBA", abbr: "UTAH", name: "Utah Jazz", short_name: "Jazz", logo: "https://a.espncdn.com/i/teamlogos/nba/500/utah.png" },
  { id: "nba_wsh", league: "NBA", abbr: "WSH", name: "Washington Wizards", short_name: "Wizards", logo: "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png" },
];

export const DEFAULT_CATALOG: SportsCatalog = {
  leagues: ["NFL", "NBA"],
  streaming_services: DEFAULT_STREAMING_SERVICES,
  teams: DEFAULT_TEAMS,
};

const DEFAULT_PREFS: SportsPreferences = {
  streaming_services: [],
  tracked_teams: [],
  show_in_queue: true,
  setup_completed: false,
};

function prefsKey(ownerId: string): string {
  return `sports_prefs:${ownerId}`;
}

export function toLocalDateKey(dt: Date): string {
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function getActiveScheduleDateKeys(now: Date = new Date()): string[] {
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (base.getDay() === 5) {
    // Friday: include Friday, Saturday, and Sunday
    const sat = new Date(base);
    sat.setDate(base.getDate() + 1);
    const sun = new Date(base);
    sun.setDate(base.getDate() + 2);
    return [toLocalDateKey(base), toLocalDateKey(sat), toLocalDateKey(sun)];
  }
  return [toLocalDateKey(base)];
}

export function filterGamesForActiveWindow(games: SportsGame[], now: Date = new Date()): SportsGame[] {
  const allowedKeys = new Set(getActiveScheduleDateKeys(now));
  return games.filter((game) => {
    if (game.is_live) return true;
    const dt = new Date(game.start_time);
    if (isNaN(dt.getTime())) return true;
    return allowedKeys.has(toLocalDateKey(dt));
  });
}

export const sportsService = {
  getInstantPreferences(ownerId: string): SportsPreferences {
    try {
      if (typeof localStorage === "undefined") return { ...DEFAULT_PREFS };
      const raw = localStorage.getItem(prefsKey(ownerId));
      if (!raw) return { ...DEFAULT_PREFS };
      const v = JSON.parse(raw) as Partial<SportsPreferences>;
      return {
        streaming_services: Array.isArray(v.streaming_services) ? v.streaming_services : [],
        tracked_teams: Array.isArray(v.tracked_teams) ? v.tracked_teams : [],
        show_in_queue: v.show_in_queue !== undefined ? Boolean(v.show_in_queue) : true,
        setup_completed: Boolean(v.setup_completed),
        updated_at: v.updated_at,
      };
    } catch {
      return { ...DEFAULT_PREFS };
    }
  },

  getInstantSchedule(): SportsGame[] {
    try {
      if (typeof localStorage === "undefined") return [];
      const raw = localStorage.getItem("cinequeue_sports_schedule");
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? filterGamesForActiveWindow(parsed as SportsGame[]) : [];
    } catch {
      return [];
    }
  },

  async getLocalPreferences(ownerId: string): Promise<SportsPreferences> {
    const rec = await db.localMetadata.get(prefsKey(ownerId));
    if (!rec || !rec.value || typeof rec.value !== "object") {
      return this.getInstantPreferences(ownerId);
    }
    const v = rec.value as Partial<SportsPreferences>;
    const prefs: SportsPreferences = {
      streaming_services: Array.isArray(v.streaming_services) ? v.streaming_services : [],
      tracked_teams: Array.isArray(v.tracked_teams) ? v.tracked_teams : [],
      show_in_queue: v.show_in_queue !== undefined ? Boolean(v.show_in_queue) : true,
      setup_completed: Boolean(v.setup_completed),
      updated_at: v.updated_at || rec.updatedAt,
    };
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(prefsKey(ownerId), JSON.stringify(prefs));
      }
    } catch {
      // Ignore storage errors
    }
    return prefs;
  },

  async savePreferences(
    ownerId: string,
    patch: Partial<SportsPreferences>,
    isCloudAuthenticated = false
  ): Promise<SportsPreferences> {
    const current = await this.getLocalPreferences(ownerId);
    const nowIso = new Date().toISOString();
    const updated: SportsPreferences = {
      streaming_services: patch.streaming_services ?? current.streaming_services,
      tracked_teams: patch.tracked_teams ?? current.tracked_teams,
      show_in_queue: patch.show_in_queue !== undefined ? patch.show_in_queue : current.show_in_queue,
      setup_completed: patch.setup_completed !== undefined ? patch.setup_completed : true,
      updated_at: nowIso,
    };

    await db.localMetadata.put({
      key: prefsKey(ownerId),
      value: updated,
      updatedAt: nowIso,
    });
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(prefsKey(ownerId), JSON.stringify(updated));
      }
    } catch {
      // Ignore storage errors
    }

    if (isCloudAuthenticated && ownerId !== "guest_local" && navigator.onLine) {
      try {
        const serverSaved = await api.saveSportsPreferences(updated);
        await db.localMetadata.put({
          key: prefsKey(ownerId),
          value: serverSaved,
          updatedAt: serverSaved.updated_at || nowIso,
        });
        try {
          if (typeof localStorage !== "undefined") {
            localStorage.setItem(prefsKey(ownerId), JSON.stringify(serverSaved));
          }
        } catch {
          // Ignore storage errors
        }
        return serverSaved;
      } catch (err) {
        console.warn("Could not sync sports preferences to cloud, kept locally:", err);
      }
    }

    return updated;
  },

  async syncPreferencesFromServer(ownerId: string): Promise<SportsPreferences> {
    const local = await this.getLocalPreferences(ownerId);
    if (ownerId === "guest_local" || !navigator.onLine) {
      return local;
    }
    try {
      const remote = await api.sportsPreferences();
      if (remote.setup_completed && (!local.setup_completed || (remote.updated_at && (!local.updated_at || remote.updated_at >= local.updated_at)))) {
        await db.localMetadata.put({
          key: prefsKey(ownerId),
          value: remote,
          updatedAt: remote.updated_at || new Date().toISOString(),
        });
        try {
          if (typeof localStorage !== "undefined") {
            localStorage.setItem(prefsKey(ownerId), JSON.stringify(remote));
          }
        } catch {
          // Ignore storage errors
        }
        return remote;
      } else if (local.setup_completed && !remote.setup_completed) {
        const pushed = await api.saveSportsPreferences(local);
        return pushed;
      }
      return remote.setup_completed ? remote : local;
    } catch {
      return local;
    }
  },

  async getCatalog(): Promise<SportsCatalog> {
    if (navigator.onLine) {
      try {
        const cat = await api.sportsCatalog();
        await db.localMetadata.put({
          key: "sports_catalog",
          value: cat,
          updatedAt: new Date().toISOString(),
        });
        return cat;
      } catch {
        // Fallback to cache or default
      }
    }
    const cached = await db.localMetadata.get("sports_catalog");
    if (cached && cached.value) {
      return cached.value as SportsCatalog;
    }
    return DEFAULT_CATALOG;
  },

  async getSchedule(trackedTeams: string[] = [], forceRefresh = false): Promise<SportsGame[]> {
    if (navigator.onLine) {
      try {
        const res = await api.sportsSchedule(trackedTeams, forceRefresh);
        if (res.games && res.games.length > 0) {
          const windowed = filterGamesForActiveWindow(res.games);
          await db.localMetadata.put({
            key: "sports_schedule",
            value: windowed,
            updatedAt: new Date().toISOString(),
          });
          try {
            if (typeof localStorage !== "undefined") {
              localStorage.setItem("cinequeue_sports_schedule", JSON.stringify(windowed));
            }
          } catch {
            // Ignore storage errors
          }
          return windowed;
        }
      } catch {
        // Fallback to cached schedule
      }
    }
    const cached = await db.localMetadata.get("sports_schedule");
    if (cached && Array.isArray(cached.value)) {
      return filterGamesForActiveWindow(cached.value as SportsGame[]);
    }
    return [];
  },
};
