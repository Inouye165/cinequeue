import React, { useMemo, useState } from "react";
import type { SportsCatalog, SportsGame, SportsLeague, SportsPreferences, SportsTeam } from "../types";
import { DEFAULT_TEAMS, toLocalDateKey } from "../services/sportsService";

interface SportsTabProps {
  catalog: SportsCatalog;
  games: SportsGame[];
  preferences: SportsPreferences;
  loading: boolean;
  onSavePreferences: (patch: Partial<SportsPreferences>) => Promise<void>;
  onRefreshSchedule: () => Promise<void>;
  isSetupModalOpen?: boolean;
  onSetSetupModalOpen?: (open: boolean) => void;
}

const CATALOG_LOGO_BY_ID: Record<string, string> = Object.fromEntries(
  DEFAULT_TEAMS.map((t) => [t.id, t.logo])
);

export function resolveTeamLogo(team: SportsTeam): string {
  if (team.logo && team.logo.trim()) return team.logo;
  if (team.id && CATALOG_LOGO_BY_ID[team.id]) return CATALOG_LOGO_BY_ID[team.id];
  const fallbackKey = `${team.league.toLowerCase()}_${team.abbr.toLowerCase()}`;
  return CATALOG_LOGO_BY_ID[fallbackKey] || "";
}

export function resolveTeamRecord(team: SportsTeam): string {
  if (!team.record) return "0-0";
  if (typeof team.record === "object") {
    const val = (team.record as any).displayValue ?? (team.record as any).summary ?? (team.record as any).value;
    return val ? String(val) : "0-0";
  }
  const clean = String(team.record).trim();
  return clean || "0-0";
}

export function formatGameTime(isoString: string, statusDetail?: string): string {
  try {
    const dt = new Date(isoString);
    if (isNaN(dt.getTime())) return statusDetail || "Scheduled";
    const now = new Date();
    const isToday = toLocalDateKey(dt) === toLocalDateKey(now);
    const datePart = dt.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    const timePart = dt.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    return isToday ? `Today, ${datePart} · ${timePart}` : `${datePart} · ${timePart}`;
  } catch {
    return statusDetail || "Scheduled";
  }
}

export function formatDayBadge(isoString: string): { text: string; isToday: boolean } {
  try {
    const dt = new Date(isoString);
    if (isNaN(dt.getTime())) return { text: "GAME DAY", isToday: false };
    const now = new Date();
    if (toLocalDateKey(dt) === toLocalDateKey(now)) {
      const timePart = dt.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      });
      return { text: `TODAY · ${timePart}`, isToday: true };
    }
    return {
      text: dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }).toUpperCase(),
      isToday: false,
    };
  } catch {
    return { text: "GAME DAY", isToday: false };
  }
}

interface SportsGameCardProps {
  game: SportsGame;
  userServices: Set<string>;
  trackedTeams: Set<string>;
  onToggleTrackTeam?: (teamId: string) => void;
  onToggleService?: (serviceId: string) => void;
  onOpenSetupModal?: () => void;
  compactQueueMode?: boolean;
  onOpenSportsTab?: () => void;
}

export const SportsGameCard: React.FC<SportsGameCardProps> = ({
  game,
  userServices,
  trackedTeams,
  onToggleTrackTeam,
  onToggleService,
  onOpenSetupModal,
  compactQueueMode = false,
  onOpenSportsTab,
}) => {
  const [awayLogoErr, setAwayLogoErr] = useState(false);
  const [homeLogoErr, setHomeLogoErr] = useState(false);

  const matchingServices = game.streaming_services.filter((s) => userServices.has(s.id));
  const isAvailableOnUserServices = matchingServices.length > 0;
  const awayTracked = trackedTeams.has(game.away_team.id);
  const homeTracked = trackedTeams.has(game.home_team.id);

  const awayLogo = resolveTeamLogo(game.away_team);
  const homeLogo = resolveTeamLogo(game.home_team);
  const awayRecord = resolveTeamRecord(game.away_team);
  const homeRecord = resolveTeamRecord(game.home_team);

  const awayScore =
    (game.is_live || game.is_completed) && game.away_team.score !== null && game.away_team.score !== undefined
      ? typeof game.away_team.score === "object"
        ? (game.away_team.score as any).displayValue ?? (game.away_team.score as any).value ?? ""
        : String(game.away_team.score)
      : null;

  const homeScore =
    (game.is_live || game.is_completed) && game.home_team.score !== null && game.home_team.score !== undefined
      ? typeof game.home_team.score === "object"
        ? (game.home_team.score as any).displayValue ?? (game.home_team.score as any).value ?? ""
        : String(game.home_team.score)
      : null;

  const dayBadge = formatDayBadge(game.start_time);

  const requiredServiceNames =
    game.streaming_services.length > 0
      ? game.streaming_services.map((s) => s.short_name).join(", ")
      : game.broadcasts.length > 0
      ? game.broadcasts.join(" / ")
      : `${game.league} Broadcast`;

  const availabilityState = game.is_live
    ? "releasing_today"
    : isAvailableOnUserServices
    ? "available"
    : game.is_completed
    ? "complete"
    : userServices.size > 0
    ? "confirmed_tbd"
    : "partially_available";

  const availabilityIcon = game.is_live
    ? "●"
    : isAvailableOnUserServices
    ? "✓"
    : userServices.size > 0
    ? "✕"
    : "📺";

  const availabilityPrimaryText = game.is_live
    ? isAvailableOnUserServices
      ? `LIVE · Watch on ${matchingServices.map((s) => s.short_name).join(", ")}`
      : `LIVE NOW · ${game.status_detail}`
    : isAvailableOnUserServices
    ? `Watch on ${matchingServices.map((s) => s.short_name).join(", ")}`
    : game.is_completed
    ? "Final Score"
    : userServices.size > 0
    ? `Needs ${requiredServiceNames}`
    : `Streams on ${requiredServiceNames}`;

  const availabilitySecondaryText = `🗓️ ${formatGameTime(game.start_time, game.status_detail)}`;

  return (
    <article
      className={`media-card sports-media-card sports-game-card league-theme-${game.league.toLowerCase()} ${
        game.is_live ? "is-live" : ""
      } ${awayTracked || homeTracked ? "has-tracked-team" : ""} ${
        compactQueueMode ? "queue-sports-card" : ""
      }`}
      aria-label={`${game.league}: ${game.away_team.name} at ${game.home_team.name}`}
    >
      {/* 1. Sports Matchup Poster Area (mirrors MediaCard .poster-wrap) */}
      <div
        className={`poster-wrap sports-poster-wrap poster-league-${game.league.toLowerCase()}`}
        style={
          {
            "--away-color": game.away_team.color || (game.league === "NFL" ? "#1e3a8a" : "#7c2d12"),
            "--home-color": game.home_team.color || (game.league === "NFL" ? "#065f46" : "#312e81"),
          } as React.CSSProperties
        }
      >
        <div className="sports-poster-field-lines" aria-hidden="true" />

        {/* Top Badges: Left = League, Right = Always Game Day / Live Status */}
        <span className={`badge sports-league-badge league-${game.league.toLowerCase()}`}>
          {game.league === "NFL" ? "🏈 NFL" : "🏀 NBA"}
        </span>

        {game.is_live ? (
          <span className="badge-owned sports-poster-pill live">● LIVE</span>
        ) : game.is_completed ? (
          <span className="badge-owned sports-poster-pill final">FINAL</span>
        ) : (
          <span
            className={`badge-owned sports-poster-pill ${
              dayBadge.isToday ? "today-pill" : "day-pill"
            }`}
          >
            {dayBadge.text}
          </span>
        )}

        {/* Dual Team Contender Showcase inside the Poster */}
        <div className="sports-poster-stage">
          {/* Away Contender */}
          <div className={`sports-poster-team away ${awayTracked ? "is-tracked" : ""}`}>
            <div className="sports-poster-crest-wrap">
              <div className="sports-poster-crest">
                {awayLogo && !awayLogoErr ? (
                  <img
                    src={awayLogo}
                    alt={`${game.away_team.name} logo`}
                    className="sports-team-logo"
                    loading="lazy"
                    onError={() => setAwayLogoErr(true)}
                  />
                ) : (
                  <div className="sports-team-logo-fallback">{game.away_team.abbr}</div>
                )}
              </div>
              {onToggleTrackTeam && (
                <button
                  type="button"
                  className={`sports-star-team-btn poster-star ${awayTracked ? "active" : ""}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleTrackTeam(game.away_team.id);
                  }}
                  title={awayTracked ? `Stop tracking ${game.away_team.name}` : `Track ${game.away_team.name}`}
                  aria-label={awayTracked ? `Stop tracking ${game.away_team.name}` : `Track ${game.away_team.name}`}
                >
                  {awayTracked ? "★" : "☆"}
                </button>
              )}
            </div>
            <div className="sports-poster-team-meta">
              <span className="sports-poster-abbr">{game.away_team.abbr}</span>
              <span className="sports-poster-short-name">{game.away_team.short_name}</span>
              <span className="sports-team-record-pill" title={`Away record: ${awayRecord}`}>
                {awayRecord}
              </span>
              {awayScore !== null && <span className="sports-poster-score">{awayScore}</span>}
            </div>
          </div>

          {/* Center VS / @ Medallion */}
          <div className="sports-poster-vs-divider" aria-hidden="true">
            <span className="sports-poster-vs-line" />
            <span className="sports-poster-at-badge">@</span>
            <span className="sports-poster-vs-line" />
          </div>

          {/* Home Contender */}
          <div className={`sports-poster-team home ${homeTracked ? "is-tracked" : ""}`}>
            <div className="sports-poster-crest-wrap">
              <div className="sports-poster-crest">
                {homeLogo && !homeLogoErr ? (
                  <img
                    src={homeLogo}
                    alt={`${game.home_team.name} logo`}
                    className="sports-team-logo"
                    loading="lazy"
                    onError={() => setHomeLogoErr(true)}
                  />
                ) : (
                  <div className="sports-team-logo-fallback">{game.home_team.abbr}</div>
                )}
              </div>
              {onToggleTrackTeam && (
                <button
                  type="button"
                  className={`sports-star-team-btn poster-star ${homeTracked ? "active" : ""}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleTrackTeam(game.home_team.id);
                  }}
                  title={homeTracked ? `Stop tracking ${game.home_team.name}` : `Track ${game.home_team.name}`}
                  aria-label={homeTracked ? `Stop tracking ${game.home_team.name}` : `Track ${game.home_team.name}`}
                >
                  {homeTracked ? "★" : "☆"}
                </button>
              )}
            </div>
            <div className="sports-poster-team-meta">
              <div style={{ display: "flex", alignItems: "center", gap: "4px", justifyContent: "center" }}>
                <span className="sports-poster-abbr">{game.home_team.abbr}</span>
                <span className="sports-home-tag">HOME</span>
              </div>
              <span className="sports-poster-short-name">{game.home_team.short_name}</span>
              <span className="sports-team-record-pill" title={`Home record: ${homeRecord}`}>
                {homeRecord}
              </span>
              {homeScore !== null && <span className="sports-poster-score">{homeScore}</span>}
            </div>
          </div>
        </div>

        {/* Bottom Poster Venue / Broadcast Marquee Strip */}
        <div className="sports-poster-footer">
          <span className="sports-poster-venue">
            {game.venue ? `📍 ${game.venue}` : `${game.league} Matchup`}
          </span>
        </div>
      </div>

      {/* 2. Card Body (mirrors MediaCard .card-body structure) */}
      <div className="card-body sports-card-body">
        {/* Authoritative Availability Block Directly Below Poster */}
        <div className={`availability-block state-${availabilityState}`}>
          <div className="availability-primary">
            <span className="status-state-icon" aria-hidden="true">
              {availabilityIcon}
            </span>
            <span className="status-primary-text">{availabilityPrimaryText}</span>
          </div>
          {availabilitySecondaryText && (
            <div className="availability-secondary">{availabilitySecondaryText}</div>
          )}
        </div>

        {/* Matchup Title & Team Records Summary */}
        <div className="sports-matchup-rows">
          <div className={`sports-team-row ${awayTracked ? "tracked-team" : ""}`}>
            <div className="sports-team-identity">
              <span className="sports-team-name">{game.away_team.name}</span>
            </div>
            <div className="sports-team-right">
              <span className="sports-team-record">({awayRecord})</span>
              {awayScore !== null && <span className="sports-team-score">{awayScore}</span>}
            </div>
          </div>

          <div className={`sports-team-row ${homeTracked ? "tracked-team" : ""}`}>
            <div className="sports-team-identity">
              <span className="sports-team-name">{game.home_team.name}</span>
            </div>
            <div className="sports-team-right">
              <span className="sports-team-record">({homeRecord})</span>
              {homeScore !== null && <span className="sports-team-score">{homeScore}</span>}
            </div>
          </div>
        </div>

        {/* Metadata Row (mirrors MediaCard .card-meta-row) */}
        <div className="card-meta-row">
          <span className="meta-info" style={{ flexShrink: 0 }}>
            {game.league} · {game.away_team.abbr} @ {game.home_team.abbr}
          </span>
          {game.broadcasts.length > 0 && (
            <span className="sports-broadcast-note" title={`TV: ${game.broadcasts.join(" / ")}`}>
              📺 {game.broadcasts.slice(0, 2).join(" / ")}
            </span>
          )}
        </div>

        {/* Streaming Services Pills */}
        <div className="sports-streaming-footer">
          <div className="sports-services-list">
            {game.streaming_services.map((svc) => {
              const owned = userServices.has(svc.id);
              if (onToggleService) {
                return (
                  <button
                    key={svc.id}
                    type="button"
                    className={`sports-service-badge interactive ${owned ? "owned" : "unowned"}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleService(svc.id);
                    }}
                    aria-label={
                      owned
                        ? `Remove ${svc.name} from my streaming services`
                        : `Add ${svc.name} to my streaming services`
                    }
                    title={
                      owned
                        ? `Available on your ${svc.name} subscription (click to remove)`
                        : `Click to add ${svc.name} (${svc.description}) to your services`
                    }
                  >
                    {owned ? "✓ " : "+ "}
                    {svc.short_name}
                  </button>
                );
              }
              return (
                <span
                  key={svc.id}
                  className={`sports-service-badge ${owned ? "owned" : "unowned"}`}
                  title={
                    owned
                      ? `Available on your ${svc.name} subscription`
                      : `Streaming on ${svc.name} (${svc.description})`
                  }
                >
                  {owned ? "✓ " : ""}
                  {svc.short_name}
                </span>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginLeft: "auto" }}>
            {compactQueueMode && onOpenSetupModal && (
              <button
                type="button"
                className="sports-card-link-btn"
                onClick={onOpenSetupModal}
                title="Add or remove streaming services"
              >
                ⚙️ Services
              </button>
            )}
            {compactQueueMode && onOpenSportsTab && (
              <button
                type="button"
                className="sports-card-link-btn"
                onClick={onOpenSportsTab}
                title="Open Sports tab to see all games"
              >
                All Games →
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
};

export interface SportsSetupModalProps {
  isOpen: boolean;
  catalog: SportsCatalog;
  preferences: SportsPreferences;
  onSavePreferences: (patch: Partial<SportsPreferences>) => Promise<void>;
  onClose: () => void;
}

export const SportsSetupModal: React.FC<SportsSetupModalProps> = ({
  isOpen,
  catalog,
  preferences,
  onSavePreferences,
  onClose,
}) => {
  const [teamSearchQuery, setTeamSearchQuery] = useState("");
  const [modalLeagueTab, setModalLeagueTab] = useState<SportsLeague>("NFL");

  const userServicesSet = useMemo(
    () => new Set(preferences.streaming_services),
    [preferences.streaming_services]
  );

  const trackedTeamsSet = useMemo(
    () => new Set(preferences.tracked_teams),
    [preferences.tracked_teams]
  );

  const modalTeams = useMemo(() => {
    const q = teamSearchQuery.trim().toLowerCase();
    return catalog.teams.filter((t) => {
      if (t.league !== modalLeagueTab) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.abbr.toLowerCase().includes(q) ||
        t.short_name.toLowerCase().includes(q)
      );
    });
  }, [catalog.teams, modalLeagueTab, teamSearchQuery]);

  if (!isOpen) return null;

  const handleToggleService = async (serviceId: string) => {
    const next = new Set(preferences.streaming_services);
    if (next.has(serviceId)) {
      next.delete(serviceId);
    } else {
      next.add(serviceId);
    }
    await onSavePreferences({
      streaming_services: Array.from(next),
      setup_completed: true,
    });
  };

  const handleToggleTeam = async (teamId: string) => {
    const next = new Set(preferences.tracked_teams);
    if (next.has(teamId)) {
      next.delete(teamId);
    } else {
      next.add(teamId);
    }
    await onSavePreferences({
      tracked_teams: Array.from(next),
      setup_completed: true,
    });
  };

  const handleToggleShowInQueue = async () => {
    await onSavePreferences({
      show_in_queue: !preferences.show_in_queue,
      setup_completed: true,
    });
  };

  const handleDone = async () => {
    await onSavePreferences({ setup_completed: true });
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={() => void handleDone()}>
      <div
        className="modal sports-setup-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sports-setup-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sports-modal-header">
          <div>
            <h2 id="sports-setup-title" style={{ margin: 0 }}>
              🏈🏀 Set Up Your Sports &amp; Streaming Services
            </h2>
            <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              Select the streaming services you subscribe to and the teams you follow. Click any service to add or remove it anytime — <strong>My Queue</strong> only shows games you can watch.
            </p>
          </div>
          <button
            type="button"
            className="close-btn"
            onClick={() => void handleDone()}
            aria-label="Close setup"
          >
            ✕
          </button>
        </div>

        <div className="sports-modal-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
            <h3 style={{ margin: 0 }}>
              1. My Streaming Services ({preferences.streaming_services.length} active)
            </h3>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Tap a card to add (+ Add) or remove (✓ Added)
            </span>
          </div>
          <div className="sports-services-setup-grid">
            {catalog.streaming_services.map((svc) => {
              const selected = userServicesSet.has(svc.id);
              return (
                <button
                  key={svc.id}
                  type="button"
                  className={`sports-service-card-btn ${selected ? "selected" : ""}`}
                  onClick={() => void handleToggleService(svc.id)}
                  aria-pressed={selected}
                >
                  <div className="sports-service-card-top">
                    <strong>{svc.name}</strong>
                    <span className="sports-service-check">{selected ? "✓ Added" : "+ Add"}</span>
                  </div>
                  <span className="sports-service-desc">{svc.description}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="sports-modal-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", marginBottom: "10px" }}>
            <h3 style={{ margin: 0 }}>2. Follow Your Teams ({preferences.tracked_teams.length} selected)</h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              <div className="queue-filter-chips">
                {(["NFL", "NBA"] as const).map((lg) => (
                  <button
                    key={lg}
                    type="button"
                    className={`filter-chip ${modalLeagueTab === lg ? "active" : ""}`}
                    onClick={() => setModalLeagueTab(lg)}
                  >
                    {lg === "NFL" ? "🏈 NFL (32)" : "🏀 NBA (30)"}
                  </button>
                ))}
              </div>
              <input
                type="search"
                placeholder="Filter teams..."
                value={teamSearchQuery}
                onChange={(e) => setTeamSearchQuery(e.target.value)}
                className="sports-team-search-input"
              />
            </div>
          </div>

          <div className="sports-teams-setup-grid">
            {modalTeams.map((team) => {
              const isTracked = trackedTeamsSet.has(team.id);
              return (
                <button
                  key={team.id}
                  type="button"
                  className={`sports-team-select-btn ${isTracked ? "selected" : ""}`}
                  onClick={() => void handleToggleTeam(team.id)}
                  aria-pressed={isTracked}
                >
                  {team.logo ? (
                    <img src={team.logo} alt="" className="sports-team-setup-logo" loading="lazy" />
                  ) : (
                    <span className="sports-team-logo-fallback">{team.abbr}</span>
                  )}
                  <span className="sports-team-setup-name">{team.name}</span>
                  <span className="sports-team-setup-star">{isTracked ? "★" : "+"}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="sports-modal-footer">
          <label className="sports-queue-toggle">
            <input
              type="checkbox"
              checked={preferences.show_in_queue}
              onChange={() => void handleToggleShowInQueue()}
            />
            <span>Show watchable games for my tracked teams in <strong>My Queue</strong></span>
          </label>
          <button
            type="button"
            className="pill-button primary"
            onClick={() => void handleDone()}
          >
            Done &amp; Save
          </button>
        </div>
      </div>
    </div>
  );
};

export const SportsTab: React.FC<SportsTabProps> = ({
  catalog,
  games,
  preferences,
  loading,
  onSavePreferences,
  onRefreshSchedule,
  isSetupModalOpen: externalSetupModalOpen,
  onSetSetupModalOpen,
}) => {
  const [serviceFilter, setServiceFilter] = useState<"all" | "my_services">("all");
  const [teamFilter, setTeamFilter] = useState<"all" | "my_teams">("all");
  const [leagueFilter, setLeagueFilter] = useState<"ALL" | SportsLeague>("ALL");
  const [dayFilter, setDayFilter] = useState<string>("ALL");
  const [internalSetupModalOpen, setInternalSetupModalOpen] = useState(false);

  const isSetupModalOpen =
    externalSetupModalOpen !== undefined ? externalSetupModalOpen : internalSetupModalOpen;
  const setIsSetupModalOpen = onSetSetupModalOpen || setInternalSetupModalOpen;

  // Show onboarding prompt automatically if user hasn't set up their streaming services yet
  const showOnboardingPrompt = !preferences.setup_completed || isSetupModalOpen;

  const userServicesSet = useMemo(
    () => new Set(preferences.streaming_services),
    [preferences.streaming_services]
  );

  const trackedTeamsSet = useMemo(
    () => new Set(preferences.tracked_teams),
    [preferences.tracked_teams]
  );

  // Extract distinct local days available in the current game window (Today, or Fri/Sat/Sun on Friday)
  const availableDayTabs = useMemo(() => {
    const map = new Map<string, string>();
    const todayKey = toLocalDateKey(new Date());
    for (const g of games) {
      const dt = new Date(g.start_time);
      if (isNaN(dt.getTime())) continue;
      const key = toLocalDateKey(dt);
      if (!map.has(key)) {
        const label =
          key === todayKey
            ? `Today (${dt.toLocaleDateString(undefined, { weekday: "short" })})`
            : dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
        map.set(key, label);
      }
    }
    return Array.from(map.entries()).map(([key, label]) => ({ key, label }));
  }, [games]);

  const isWeekendSlate = new Date().getDay() === 5 || availableDayTabs.length > 1;

  const handleToggleService = async (serviceId: string) => {
    const next = new Set(preferences.streaming_services);
    if (next.has(serviceId)) {
      next.delete(serviceId);
    } else {
      next.add(serviceId);
    }
    await onSavePreferences({
      streaming_services: Array.from(next),
      setup_completed: true,
    });
  };

  const handleToggleTeam = async (teamId: string) => {
    const next = new Set(preferences.tracked_teams);
    if (next.has(teamId)) {
      next.delete(teamId);
    } else {
      next.add(teamId);
    }
    await onSavePreferences({
      tracked_teams: Array.from(next),
      setup_completed: true,
    });
  };

  const handleToggleShowInQueue = async () => {
    await onSavePreferences({
      show_in_queue: !preferences.show_in_queue,
      setup_completed: true,
    });
  };

  const filteredGames = useMemo(() => {
    return games.filter((game) => {
      if (leagueFilter !== "ALL" && game.league !== leagueFilter) {
        return false;
      }
      if (dayFilter !== "ALL") {
        const dt = new Date(game.start_time);
        if (!isNaN(dt.getTime()) && toLocalDateKey(dt) !== dayFilter) {
          return false;
        }
      }
      if (serviceFilter === "my_services") {
        const hasService = game.streaming_service_ids.some((id) => userServicesSet.has(id));
        if (!hasService) return false;
      }
      if (teamFilter === "my_teams") {
        const hasTeam =
          trackedTeamsSet.has(game.home_team.id) || trackedTeamsSet.has(game.away_team.id);
        if (!hasTeam) return false;
      }
      return true;
    });
  }, [games, leagueFilter, dayFilter, serviceFilter, teamFilter, userServicesSet, trackedTeamsSet]);

  const trackedTeamObjects = useMemo(
    () => catalog.teams.filter((t) => trackedTeamsSet.has(t.id)),
    [catalog.teams, trackedTeamsSet]
  );

  return (
    <div className="sports-hub-container">
      {/* Top summary & quick-manage bar */}
      <div className="sports-control-panel">
        <div className="sports-window-banner">
          <div className="sports-window-info">
            <span className="sports-window-eyebrow">
              {isWeekendSlate ? "📅 FRIDAY & WEEKEND SLATE" : "📅 TODAY'S GAME SLATE"}
            </span>
            <span className="sports-window-sub">
              {isWeekendSlate
                ? `Showing Friday, Saturday & Sunday matchups (${filteredGames.length} games)`
                : `Showing today's live & upcoming matchups (${filteredGames.length} games)`}
            </span>
          </div>

          <div className="sports-actions-right">
            <label
              className="sports-queue-toggle"
              title="Automatically show upcoming games for your tracked teams that you can watch on your streaming services in My Queue"
            >
              <input
                type="checkbox"
                checked={preferences.show_in_queue}
                onChange={() => void handleToggleShowInQueue()}
              />
              <span>Show Watchable Games in Queue</span>
            </label>
            <button
              type="button"
              className="pill-button primary sports-manage-btn"
              onClick={() => setIsSetupModalOpen(true)}
            >
              📺 Manage Streaming Services &amp; Teams ({preferences.streaming_services.length} services · {preferences.tracked_teams.length} teams)
            </button>
            <button
              type="button"
              className="pill-button secondary sports-refresh-btn"
              onClick={() => void onRefreshSchedule()}
              disabled={loading}
              title="Refresh live scores and schedule"
            >
              {loading ? "Refreshing..." : "↻ Refresh"}
            </button>
          </div>
        </div>

        <div className="sports-summary-row">
          <div className="sports-summary-group">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
              <span className="sports-summary-label">
                📺 Your Streaming Services ({preferences.streaming_services.length} active — tap any service to add or remove):
              </span>
              <button
                type="button"
                className="sports-add-team-inline-btn"
                onClick={() => setIsSetupModalOpen(true)}
              >
                ⚙️ Open Services &amp; Teams Setup
              </button>
            </div>
            <div className="sports-active-pills">
              {catalog.streaming_services.map((svc) => {
                const isSelected = userServicesSet.has(svc.id);
                return (
                  <button
                    key={svc.id}
                    type="button"
                    className={`sports-service-toggle-chip ${isSelected ? "active" : ""}`}
                    onClick={() => void handleToggleService(svc.id)}
                    aria-pressed={isSelected}
                    title={isSelected ? `Click to remove ${svc.name}` : `Click to add ${svc.name}`}
                  >
                    {isSelected ? "✓ " : "+ "}
                    {svc.short_name}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Tracked teams quick bar */}
        <div className="sports-tracked-teams-bar">
          <span className="sports-summary-label">Tracked Teams:</span>
          {trackedTeamObjects.length > 0 ? (
            <div className="sports-tracked-team-chips">
              {trackedTeamObjects.map((team) => (
                <span key={team.id} className="sports-tracked-team-pill">
                  {team.logo && <img src={team.logo} alt="" className="sports-mini-logo" />}
                  <span>{team.abbr}</span>
                  <button
                    type="button"
                    className="sports-pill-remove"
                    onClick={() => void handleToggleTeam(team.id)}
                    aria-label={`Remove ${team.name}`}
                    title={`Stop tracking ${team.name}`}
                  >
                    ×
                  </button>
                </span>
              ))}
              <button
                type="button"
                className="sports-add-team-inline-btn"
                onClick={() => setIsSetupModalOpen(true)}
              >
                + Add/Edit Teams
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                No teams tracked yet. Star a team on any game poster or select your teams!
              </span>
              <button
                type="button"
                className="sports-add-team-inline-btn"
                onClick={() => setIsSetupModalOpen(true)}
              >
                + Pick Teams
              </button>
            </div>
          )}
        </div>

        {/* Filter bar: Streaming Services Filter, Teams Filter, League Filter, Day Filter */}
        <div className="sports-filters-bar">
          <div className="queue-filter-chips" role="group" aria-label="Streaming Service Filter">
            <button
              type="button"
              className={`filter-chip ${serviceFilter === "all" ? "active" : ""}`}
              onClick={() => setServiceFilter("all")}
              aria-pressed={serviceFilter === "all"}
            >
              All Streaming Services
            </button>
            <button
              type="button"
              className={`filter-chip ${serviceFilter === "my_services" ? "active" : ""}`}
              onClick={() => setServiceFilter("my_services")}
              aria-pressed={serviceFilter === "my_services"}
            >
              My Services Only ({preferences.streaming_services.length})
            </button>
          </div>

          <div className="queue-filter-chips" role="group" aria-label="Teams Filter">
            <button
              type="button"
              className={`filter-chip ${teamFilter === "all" ? "active" : ""}`}
              onClick={() => setTeamFilter("all")}
              aria-pressed={teamFilter === "all"}
            >
              All Teams
            </button>
            <button
              type="button"
              className={`filter-chip ${teamFilter === "my_teams" ? "active" : ""}`}
              onClick={() => setTeamFilter("my_teams")}
              aria-pressed={teamFilter === "my_teams"}
            >
              My Teams Only ({preferences.tracked_teams.length})
            </button>
          </div>

          <div className="queue-filter-chips" role="group" aria-label="League Filter">
            {(["ALL", "NFL", "NBA"] as const).map((lg) => (
              <button
                key={lg}
                type="button"
                className={`filter-chip ${leagueFilter === lg ? "active" : ""}`}
                onClick={() => setLeagueFilter(lg)}
                aria-pressed={leagueFilter === lg}
              >
                {lg === "ALL" ? "All Leagues" : lg === "NFL" ? "🏈 NFL" : "🏀 NBA"}
              </button>
            ))}
          </div>

          {availableDayTabs.length > 1 && (
            <div className="queue-filter-chips" role="group" aria-label="Day Filter">
              <button
                type="button"
                className={`filter-chip ${dayFilter === "ALL" ? "active" : ""}`}
                onClick={() => setDayFilter("ALL")}
                aria-pressed={dayFilter === "ALL"}
              >
                All Weekend
              </button>
              {availableDayTabs.map((d) => (
                <button
                  key={d.key}
                  type="button"
                  className={`filter-chip ${dayFilter === d.key ? "active" : ""}`}
                  onClick={() => setDayFilter(d.key)}
                  aria-pressed={dayFilter === d.key}
                >
                  {d.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Games Grid — uses .media-grid for identical card layout & sizing as movies/TV */}
      {filteredGames.length > 0 ? (
        <div className="media-grid sports-games-grid">
          {filteredGames.map((game) => (
            <SportsGameCard
              key={game.id}
              game={game}
              userServices={userServicesSet}
              trackedTeams={trackedTeamsSet}
              onToggleTrackTeam={(teamId) => void handleToggleTeam(teamId)}
              onToggleService={(serviceId) => void handleToggleService(serviceId)}
            />
          ))}
        </div>
      ) : (
        <div className="empty-state">
          {serviceFilter === "my_services" && preferences.streaming_services.length === 0 ? (
            <div>
              <p>You haven&apos;t selected any streaming services yet.</p>
              <button
                type="button"
                className="pill-button primary"
                onClick={() => setIsSetupModalOpen(true)}
                style={{ marginTop: "8px" }}
              >
                Select My Streaming Services
              </button>
            </div>
          ) : teamFilter === "my_teams" && preferences.tracked_teams.length === 0 ? (
            <div>
              <p>You haven&apos;t tracked any NFL or NBA teams yet.</p>
              <button
                type="button"
                className="pill-button primary"
                onClick={() => setIsSetupModalOpen(true)}
                style={{ marginTop: "8px" }}
              >
                Choose My Teams
              </button>
            </div>
          ) : (
            <div>
              <p>No games in the active slate match your current filters.</p>
              <button
                type="button"
                className="pill-button secondary"
                onClick={() => {
                  setServiceFilter("all");
                  setTeamFilter("all");
                  setLeagueFilter("ALL");
                  setDayFilter("ALL");
                }}
                style={{ marginTop: "8px" }}
              >
                Reset Filters
              </button>
            </div>
          )}
        </div>
      )}

      {/* Onboarding / Manage Services & Teams Modal */}
      <SportsSetupModal
        isOpen={showOnboardingPrompt}
        catalog={catalog}
        preferences={preferences}
        onSavePreferences={onSavePreferences}
        onClose={() => setIsSetupModalOpen(false)}
      />
    </div>
  );
};
