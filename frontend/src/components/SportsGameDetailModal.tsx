import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { SportsGame, SportsTeam } from "../types";

interface SportsGameDetailModalProps {
  game: SportsGame | null;
  onClose: () => void;
  userServices: Set<string>;
  trackedTeams: Set<string>;
  onToggleTrackTeam?: (teamId: string) => void;
  onToggleService?: (serviceId: string) => void;
  onRefreshScores?: () => Promise<void> | void;
  isRefreshing?: boolean;
}

function resolveTeamLogo(team: SportsTeam): string {
  if (team.logo && team.logo.trim()) return team.logo.trim();
  const league = (team.league || "").toLowerCase();
  const abbr = (team.abbr || "").toLowerCase();
  if ((league === "nfl" || league === "nba") && abbr && abbr !== "tbd") {
    return `https://a.espncdn.com/i/teamlogos/${league}/500/${abbr}.png`;
  }
  return "";
}

function resolveScore(team: SportsTeam, showScore: boolean): string | null {
  if (!showScore || team.score === null || team.score === undefined) return null;
  if (typeof team.score === "object") {
    const obj = team.score as Record<string, unknown>;
    return String(obj.displayValue ?? obj.value ?? "");
  }
  return String(team.score);
}

function formatFullDateTime(iso: string): string {
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return dt.toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export const SportsGameDetailModal: React.FC<SportsGameDetailModalProps> = ({
  game,
  onClose,
  userServices,
  trackedTeams,
  onToggleTrackTeam,
  onToggleService,
  onRefreshScores,
  isRefreshing = false,
}) => {
  const [awayLogoErr, setAwayLogoErr] = useState(false);
  const [homeLogoErr, setHomeLogoErr] = useState(false);
  const [localRefreshing, setLocalRefreshing] = useState(false);
  const [lastUpdatedLabel, setLastUpdatedLabel] = useState<string | null>(null);

  useEffect(() => {
    setAwayLogoErr(false);
    setHomeLogoErr(false);
  }, [game?.id]);

  useEffect(() => {
    if (!game) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [game, onClose]);

  const handleRefresh = async () => {
    if (!onRefreshScores || localRefreshing || isRefreshing) return;
    setLocalRefreshing(true);
    try {
      await onRefreshScores();
      setLastUpdatedLabel(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }));
    } finally {
      setLocalRefreshing(false);
    }
  };

  // Auto-poll live scores every 20s while the full-screen card is open
  useEffect(() => {
    if (!game || !game.is_live || !onRefreshScores) return;
    const timer = window.setInterval(() => {
      void Promise.resolve(onRefreshScores()).then(() => {
        setLastUpdatedLabel(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }));
      });
    }, 20000);
    return () => window.clearInterval(timer);
  }, [game?.id, game?.is_live, onRefreshScores]);

  if (!game) return null;

  const showScore = game.is_live || game.is_completed;
  const awayScore = resolveScore(game.away_team, showScore);
  const homeScore = resolveScore(game.home_team, showScore);
  const awayLogo = resolveTeamLogo(game.away_team);
  const homeLogo = resolveTeamLogo(game.home_team);
  const awayTracked = trackedTeams.has(game.away_team.id);
  const homeTracked = trackedTeams.has(game.home_team.id);
  const matchingServices = game.streaming_services.filter((s) => userServices.has(s.id));
  const refreshing = isRefreshing || localRefreshing;

  const awayLines = game.away_team.linescores || [];
  const homeLines = game.home_team.linescores || [];
  const periodCount = Math.max(awayLines.length, homeLines.length);

  const periodLabel = (idx: number) => {
    if (idx < 4) return `Q${idx + 1}`;
    return idx === 4 ? "OT" : `OT${idx - 3}`;
  };

  const content = (
    <div
      className="sports-game-fullscreen-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`${game.away_team.name} at ${game.home_team.name} scoreboard`}
    >
      <div
        className={`sports-game-fullscreen-modal league-theme-${game.league.toLowerCase()}`}
        style={
          {
            "--away-color": game.away_team.color || (game.league === "NFL" ? "#1e3a8a" : "#7c2d12"),
            "--home-color": game.home_team.color || (game.league === "NFL" ? "#065f46" : "#312e81"),
          } as React.CSSProperties
        }
      >
        {/* Sticky Top Bar */}
        <header className="sports-fullscreen-topbar">
          <div className="sports-fullscreen-topbar-left">
            <span className={`sports-league-badge-inline league-${game.league.toLowerCase()}`}>
              {game.league === "NFL" ? "🏈 NFL" : "🏀 NBA"}
            </span>
            {game.is_live ? (
              <span className="sports-poster-pill live">● LIVE</span>
            ) : game.is_completed ? (
              <span className="sports-poster-pill final">FINAL</span>
            ) : (
              <span className="sports-poster-pill day-pill">SCHEDULED</span>
            )}
          </div>

          <div className="sports-fullscreen-topbar-actions">
            {onRefreshScores && (
              <button
                type="button"
                className="pill-button secondary sports-fullscreen-refresh-btn"
                onClick={() => void handleRefresh()}
                disabled={refreshing}
                aria-label="Refresh live score"
              >
                {refreshing ? "↻ Updating..." : "↻ Refresh Score"}
              </button>
            )}
            <button
              type="button"
              className="sports-fullscreen-close-btn"
              onClick={onClose}
              aria-label="Close game scoreboard"
            >
              ✕ Close
            </button>
          </div>
        </header>

        {/* Scrollable Full-Screen Body */}
        <div className="sports-fullscreen-body">
          {/* Hero Scoreboard */}
          <section className="sports-fullscreen-scoreboard">
            <div className="sports-fullscreen-team away">
              <div className="sports-fullscreen-crest">
                {awayLogo && !awayLogoErr ? (
                  <img
                    src={awayLogo}
                    alt={`${game.away_team.name} logo`}
                    onError={() => setAwayLogoErr(true)}
                  />
                ) : (
                  <div className="sports-team-logo-fallback">{game.away_team.abbr}</div>
                )}
              </div>
              <div className="sports-fullscreen-team-info">
                <span className="sports-fullscreen-abbr">{game.away_team.abbr}</span>
                <h2 className="sports-fullscreen-team-name">{game.away_team.name}</h2>
                <span className="sports-team-record-pill">
                  {game.away_team.record || "0-0"}
                </span>
              </div>
              {awayScore !== null && (
                <div className="sports-fullscreen-score" data-testid="away-score">
                  {awayScore}
                </div>
              )}
              {onToggleTrackTeam && (
                <button
                  type="button"
                  className={`pill-button secondary sports-fullscreen-track-btn ${awayTracked ? "active" : ""}`}
                  onClick={() => onToggleTrackTeam(game.away_team.id)}
                >
                  {awayTracked ? "★ Tracking" : "☆ Track Team"}
                </button>
              )}
            </div>

            <div className="sports-fullscreen-center">
              <span className="sports-fullscreen-status-detail">
                {game.is_live
                  ? game.status_detail || "LIVE"
                  : game.is_completed
                  ? game.status_detail || "FINAL"
                  : formatFullDateTime(game.start_time)}
              </span>
              <span className="sports-fullscreen-vs">VS</span>
              {game.is_live && (
                <span className="sports-fullscreen-autopoll-note">
                  Auto-updates every 20s{lastUpdatedLabel ? ` · ${lastUpdatedLabel}` : ""}
                </span>
              )}
              {!game.is_live && lastUpdatedLabel && (
                <span className="sports-fullscreen-autopoll-note">
                  Updated {lastUpdatedLabel}
                </span>
              )}
            </div>

            <div className="sports-fullscreen-team home">
              <div className="sports-fullscreen-crest">
                {homeLogo && !homeLogoErr ? (
                  <img
                    src={homeLogo}
                    alt={`${game.home_team.name} logo`}
                    onError={() => setHomeLogoErr(true)}
                  />
                ) : (
                  <div className="sports-team-logo-fallback">{game.home_team.abbr}</div>
                )}
              </div>
              <div className="sports-fullscreen-team-info">
                <div className="sports-fullscreen-abbr-row">
                  <span className="sports-fullscreen-abbr">{game.home_team.abbr}</span>
                  <span className="sports-home-tag">HOME</span>
                </div>
                <h2 className="sports-fullscreen-team-name">{game.home_team.name}</h2>
                <span className="sports-team-record-pill">
                  {game.home_team.record || "0-0"}
                </span>
              </div>
              {homeScore !== null && (
                <div className="sports-fullscreen-score" data-testid="home-score">
                  {homeScore}
                </div>
              )}
              {onToggleTrackTeam && (
                <button
                  type="button"
                  className={`pill-button secondary sports-fullscreen-track-btn ${homeTracked ? "active" : ""}`}
                  onClick={() => onToggleTrackTeam(game.home_team.id)}
                >
                  {homeTracked ? "★ Tracking" : "☆ Track Team"}
                </button>
              )}
            </div>
          </section>

          {/* Live Last Play Callout */}
          {game.last_play && (
            <section className="sports-fullscreen-card sports-last-play-card">
              <span className="sports-fullscreen-section-label">Latest Play</span>
              <p className="sports-last-play-text">{game.last_play}</p>
            </section>
          )}

          {/* Quarter / Period Box Score */}
          {periodCount > 0 && (
            <section className="sports-fullscreen-card">
              <span className="sports-fullscreen-section-label">Score by Period</span>
              <div className="sports-linescore-wrap">
                <table className="sports-linescore-table">
                  <thead>
                    <tr>
                      <th>Team</th>
                      {Array.from({ length: periodCount }, (_, idx) => (
                        <th key={idx}>{periodLabel(idx)}</th>
                      ))}
                      <th>T</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="team-cell">{game.away_team.abbr}</td>
                      {Array.from({ length: periodCount }, (_, idx) => (
                        <td key={idx}>{awayLines[idx] ?? "-"}</td>
                      ))}
                      <td className="total-cell">{awayScore ?? "-"}</td>
                    </tr>
                    <tr>
                      <td className="team-cell">{game.home_team.abbr}</td>
                      {Array.from({ length: periodCount }, (_, idx) => (
                        <td key={idx}>{homeLines[idx] ?? "-"}</td>
                      ))}
                      <td className="total-cell">{homeScore ?? "-"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Matchup Details & Where to Watch */}
          <section className="sports-fullscreen-card">
            <span className="sports-fullscreen-section-label">Game Info &amp; Where to Watch</span>
            <div className="sports-fullscreen-meta-grid">
              <div className="sports-fullscreen-meta-item">
                <span className="meta-label">Start Time</span>
                <span className="meta-val">{formatFullDateTime(game.start_time)}</span>
              </div>
              {game.venue && (
                <div className="sports-fullscreen-meta-item">
                  <span className="meta-label">Venue</span>
                  <span className="meta-val">📍 {game.venue}</span>
                </div>
              )}
              <div className="sports-fullscreen-meta-item">
                <span className="meta-label">Broadcasts</span>
                <span className="meta-val">
                  {game.broadcasts.length > 0 ? game.broadcasts.join(" / ") : `${game.league} Broadcast`}
                </span>
              </div>
              <div className="sports-fullscreen-meta-item">
                <span className="meta-label">Your Access</span>
                <span className="meta-val">
                  {matchingServices.length > 0
                    ? `✓ Watchable on ${matchingServices.map((s) => s.short_name).join(", ")}`
                    : "Tap a service below if you have it"}
                </span>
              </div>
            </div>

            {game.streaming_services.length > 0 && (
              <div className="sports-fullscreen-services">
                {game.streaming_services.map((svc) => {
                  const owned = userServices.has(svc.id);
                  if (onToggleService) {
                    return (
                      <button
                        key={svc.id}
                        type="button"
                        className={`sports-service-badge interactive ${owned ? "owned" : "unowned"}`}
                        onClick={() => onToggleService(svc.id)}
                      >
                        {owned ? "✓ " : "+ "}
                        {svc.short_name}
                      </button>
                    );
                  }
                  return (
                    <span key={svc.id} className={`sports-service-badge ${owned ? "owned" : "unowned"}`}>
                      {owned ? "✓ " : ""}
                      {svc.short_name}
                    </span>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );

  return typeof document !== "undefined" ? createPortal(content, document.body) : content;
};
