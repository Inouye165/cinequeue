import { useEffect, useRef, useState } from "react";
import type { MediaDetails, Trailer } from "../types";
import { StarRating } from "./StarRating";
import { formatPosterUrl } from "../utils/mediaUtils";

interface Props {
  details: MediaDetails;
  isOnQueue: boolean;
  isFollowing: boolean;
  isOwned: boolean;
  ownedFormat: "electronic" | "cloud" | "hard_copy" | null;
  watchFreeStreaming: boolean;
  watchOnSaleBuy: boolean;
  userRating?: number | null;
  onClose: () => void;
  onAdd: () => void;
  onRemove: () => void;
  onRate?: (rating: number) => void;
  onUpdateOwned: (item: MediaDetails, isOwned: boolean, format?: "electronic" | "cloud" | "hard_copy") => void;
  onMoveToFollowing: () => void;
  onMoveToQueue: () => void;
  onUpdateWatchOptions: (watchFreeStreaming: boolean, watchOnSaleBuy: boolean) => void;
}

function TrailerPlayer({ trailer }: { trailer: Trailer }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`trailer-card ${isExpanded ? "expanded" : ""}`}
      onClick={() => !isExpanded && setIsExpanded(true)}
    >
      {isExpanded ? (
        <div className="trailer-player-wrapper">
          <button
            className="trailer-collapse-btn"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(false);
            }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
            Collapse
          </button>
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${trailer.key}?autoplay=1&rel=0`}
            title="Official trailer"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      ) : (
        <div
          className="trailer-thumbnail-wrapper"
          style={{ backgroundImage: `url(https://img.youtube.com/vi/${trailer.key}/hqdefault.jpg)` }}
        >
          <div className="trailer-play-btn" />
          <div className="trailer-title">{trailer.name}</div>
        </div>
      )}
    </div>
  );
}

export function DetailModal({
  details,
  isOnQueue,
  isFollowing,
  isOwned,
  ownedFormat,
  watchFreeStreaming,
  watchOnSaleBuy,
  userRating,
  onClose,
  onAdd,
  onRemove,
  onRate,
  onUpdateOwned,
  onMoveToFollowing,
  onMoveToQueue,
  onUpdateWatchOptions,
}: Props) {
  const providers = details.watch_providers?.categories ?? {};
  const releaseInfo = details.release_info as Record<string, string | number | null | undefined>;
  const touchStartYRef = useRef<number | null>(null);
  const [dragOffsetY, setDragOffsetY] = useState(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      touchStartYRef.current = e.touches[0].clientY;
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartYRef.current === null) return;
    const deltaY = e.touches[0].clientY - touchStartYRef.current;
    if (deltaY > 0) {
      setDragOffsetY(Math.min(deltaY, 180));
    }
  };

  const handleTouchEnd = () => {
    if (dragOffsetY > 72) {
      setDragOffsetY(0);
      touchStartYRef.current = null;
      onClose();
      return;
    }
    setDragOffsetY(0);
    touchStartYRef.current = null;
  };

  const handleFormatChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdateOwned(details, true, e.target.value as any);
  };

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div
        className="detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${details.title} details`}
        onClick={(e) => e.stopPropagation()}
        style={dragOffsetY > 0 ? { transform: `translateY(${dragOffsetY}px)`, transition: "none" } : undefined}
      >
        <div
          className="detail-sheet-topbar"
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          <div className="mobile-sheet-handle" aria-hidden="true" />
          <button
            type="button"
            className="icon-button close-button"
            onClick={onClose}
            aria-label="Close details"
          >
            <svg
              className="close-button-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            <span className="close-button-text">Close</span>
          </button>
        </div>
        <div
          className="detail-hero"
          style={
            details.backdrop_url
              ? { backgroundImage: `url(${details.backdrop_url})` }
              : undefined
          }
        >
          <div className="detail-hero-content">
            {formatPosterUrl(details.poster_url || details.poster_path) ? (
              <img src={formatPosterUrl(details.poster_url || details.poster_path)!} alt="" />
            ) : null}
            <div>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                <p style={{ margin: 0, fontSize: "0.82rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>
                  {details.media_type === "tv" ? "TV Series" : "Movie"}
                </p>
                {isOwned && (
                  <span className="badge-owned" style={{ position: "static", boxShadow: "none" }}>
                    Owned
                  </span>
                )}
                {!isOwned && isFollowing && (
                  <span className="badge-monitoring" style={{ position: "static", boxShadow: "none", background: "var(--accent)", color: "#0b0d12" }}>
                    Monitoring
                  </span>
                )}
                {!isOwned && (isOnQueue || isFollowing) && watchFreeStreaming && details.watch_providers?.is_free_streaming && (
                  <span className="badge-alert-active free-streaming" style={{ position: "static", boxShadow: "none", background: "var(--success)", color: "#0b0d12", padding: "4px 8px", borderRadius: "4px", fontSize: "0.75rem", fontWeight: "bold" }}>
                    🎉 Free to Stream
                  </span>
                )}
                {!isOwned && (isOnQueue || isFollowing) && watchOnSaleBuy && details.watch_providers?.is_on_sale && (
                  <span className="badge-alert-active buy-sale" style={{ position: "static", boxShadow: "none", background: "var(--danger)", color: "#fff", padding: "4px 8px", borderRadius: "4px", fontSize: "0.75rem", fontWeight: "bold" }}>
                    🔥 On Sale: {details.watch_providers.buy_current_price}
                  </span>
                )}
              </div>
              <h2>{details.title}</h2>
              {details.tagline ? <p className="detail-tagline">{details.tagline}</p> : null}
              <div className="meta-row">
                {details.media_type === "tv" && details.next_season ? (
                  <div className="tv-seasons-info">
                    <span className="first-episode-date">First Episode: {details.release_date}</span>
                    <span className="next-season-date">
                      Next Season: {details.next_season.name} ({details.next_season.air_date})
                      {details.next_season.days_label && (
                        <span className="countdown" style={{ marginLeft: "6px" }}>
                          {details.next_season.days_label}
                        </span>
                      )}
                    </span>
                  </div>
                ) : (
                  <>
                    {details.days_label ? <span className="countdown">{details.days_label}</span> : null}
                    {details.release_date ? <span>{details.release_date}</span> : null}
                  </>
                )}
                {details.vote_average ? <span className="rating">★ {details.vote_average.toFixed(1)}</span> : null}
                {details.runtime_minutes ? <span>{details.runtime_minutes} min</span> : null}
              </div>
              <div className="chip-list" style={{ marginTop: 12 }}>
                {details.genres?.map((genre: string) => (
                  <span className="chip" key={genre}>
                    {genre}
                  </span>
                ))}
              </div>

              <div className="detail-rating-row" style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: "0.9rem", color: "var(--text-muted)", fontWeight: 600 }}>Your Rating:</span>
                <StarRating
                  rating={details.user_rating !== undefined ? details.user_rating : userRating}
                  onRate={onRate}
                  size="md"
                />
              </div>
              
              <div className="detail-owned-section">
                {/* Queue / Following buttons */}
                {!isOwned && (
                  <>
                    {isOnQueue && (
                      <>
                        <button type="button" className="pill-button secondary" onClick={onMoveToFollowing}>
                          Monitor Alerts
                        </button>
                        <button type="button" className="pill-button danger" onClick={onRemove}>
                          Remove from queue
                        </button>
                      </>
                    )}
                    {isFollowing && (
                      <>
                        <button type="button" className="pill-button primary" onClick={onMoveToQueue}>
                          Move to Queue
                        </button>
                        <button type="button" className="pill-button danger" onClick={onRemove}>
                          Remove from monitoring
                        </button>
                      </>
                    )}
                    {!isOnQueue && !isFollowing && (
                      <button type="button" className="pill-button primary" onClick={onAdd}>
                        Add to queue
                      </button>
                    )}
                  </>
                )}

                {/* Library controls */}
                {isOwned ? (
                  <div className="owned-controls">
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 500 }}>Format:</span>
                    <select
                      value={ownedFormat || "electronic"}
                      onChange={handleFormatChange}
                      className="owned-select"
                    >
                      <option value="electronic">Electronic</option>
                      <option value="cloud">Cloud based</option>
                      <option value="hard_copy">Hard copy</option>
                    </select>
                    <button
                      type="button"
                      className="pill-button danger"
                      onClick={() => onUpdateOwned(details, false)}
                    >
                      Remove from library
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="pill-button success"
                    onClick={() => onUpdateOwned(details, true, "electronic")}
                  >
                    + Mark as Owned
                  </button>
                )}

                {details.homepage ? (
                  <a className="pill-button secondary" href={details.homepage} target="_blank" rel="noreferrer">
                    Official site
                  </a>
                ) : null}
              </div>
              
              {!isOwned && (isOnQueue || isFollowing) && (
                <div className="watch-alerts-container" style={{ marginTop: 20, padding: "12px 16px", background: "var(--bg-elevated)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 600, display: "block", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                    Watch Alerts
                  </span>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.9rem", userSelect: "none" }}>
                      <input
                        type="checkbox"
                        checked={watchFreeStreaming}
                        onChange={(e) => onUpdateWatchOptions(e.target.checked, watchOnSaleBuy)}
                        style={{ cursor: "pointer" }}
                      />
                      Watch for free streaming
                    </label>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.9rem", userSelect: "none" }}>
                      <input
                        type="checkbox"
                        checked={watchOnSaleBuy}
                        onChange={(e) => onUpdateWatchOptions(watchFreeStreaming, e.target.checked)}
                        style={{ cursor: "pointer" }}
                      />
                      Watch for buy sales
                    </label>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="detail-content">
          {details.overview ? <p>{details.overview}</p> : null}

          {details.cast_changes && (
            (details.cast_changes.written_out?.length > 0 || details.cast_changes.returning_with_new_actors?.length > 0)
          ) ? (
            <section className="panel" style={{ padding: "20px" }}>
              <h4 className="cast-changes-title">Season {details.cast_changes.next_season} Cast Changes</h4>
              <p className="cast-changes-subtitle">
                Comparing to Season {details.cast_changes.prev_season} main cast
              </p>
              
              {details.cast_changes.returning_with_new_actors?.length > 0 && (
                <div className="cast-changes-group">
                  <h5 className="cast-changes-group-title recast">Main Characters Returning with New Actors</h5>
                  <ul className="cast-changes-list">
                    {details.cast_changes.returning_with_new_actors.map((change, idx) => (
                      <li key={idx}>
                        <strong>{change.character}</strong>: formerly played by {change.old_actor}, now played by <strong>{change.new_actor}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {details.cast_changes.written_out?.length > 0 && (
                <div className="cast-changes-group">
                  <h5 className="cast-changes-group-title written-out">Main Characters Written Out of the Show</h5>
                  <ul className="cast-changes-list">
                    {details.cast_changes.written_out.map((change, idx) => (
                      <li key={idx}>
                        <strong>{change.character}</strong> (played by {change.actor})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          ) : null}

          {details.trailers && details.trailers.length > 0 ? (
            <section className="panel" style={{ padding: "20px" }}>
              <h4 style={{ margin: "0 0 16px" }}>Official Trailer</h4>
              <div className="trailers-container">
                {details.trailers.map((trailer) => (
                  <TrailerPlayer key={trailer.key} trailer={trailer} />
                ))}
              </div>
            </section>
          ) : null}

          <div className="detail-grid">
            <section className="panel">
              <h4>Where to watch</h4>
              {providers.theatres?.length ? (
                <>
                  <strong>Theatres</strong>
                  <div className="provider-list">
                    {providers.theatres.map((p) => (
                      <span className="provider" key={p.name}>
                        {p.name}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
              {providers.streaming?.length || providers.free?.length ? (
                <>
                  {providers.streaming?.length ? (
                    <>
                      <strong>Streaming (Subscription)</strong>
                      <div className="provider-list">
                        {providers.streaming.map((p) => (
                          <span className="provider" key={p.name}>
                            {p.logo_url ? <img src={p.logo_url} alt="" /> : null}
                            {p.name}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : null}
                  {providers.free?.length ? (
                    <>
                      <strong>Streaming (Free / Ads)</strong>
                      <div className="provider-list">
                        {providers.free.map((p) => (
                          <span className="provider" key={p.name}>
                            {p.logo_url ? <img src={p.logo_url} alt="" /> : null}
                            {p.name}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : null}
                </>
              ) : (
                <>
                  <strong>Streaming</strong>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", margin: "4px 0 12px" }}>
                    No subscription or free streaming options found in the US.
                  </p>
                </>
              )}
              {providers.rent?.length ? (
                <>
                  <strong>Rent</strong>
                  <div className="provider-list">
                    {providers.rent.map((p) => (
                      <span className="provider" key={p.name}>
                        {p.logo_url ? <img src={p.logo_url} alt="" /> : null}
                        {p.name}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
              {providers.buy?.length ? (
                <>
                  <strong>Buy</strong>
                  <div className="provider-list">
                    {providers.buy.map((p) => (
                      <span className="provider" key={p.name}>
                        {p.logo_url ? <img src={p.logo_url} alt="" /> : null}
                        {p.name}
                        {p.current_price ? (
                          <span style={{ fontSize: "0.8rem", marginLeft: "4px", color: p.is_on_sale ? "var(--danger)" : "var(--text-muted)", fontWeight: p.is_on_sale ? "bold" : "normal" }}>
                            ({p.is_on_sale ? <span style={{ textDecoration: "line-through", marginRight: "4px", color: "var(--text-muted)", fontWeight: "normal" }}>{p.original_price}</span> : null}
                            {p.current_price})
                          </span>
                        ) : null}
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
              {!providers.streaming?.length &&
              !providers.free?.length &&
              !providers.rent?.length &&
              !providers.buy?.length &&
              !providers.theatres?.length ? (
                <p>No US provider data yet.</p>
              ) : null}
              {details.watch_providers?.link ? (
                <p>
                  <a href={details.watch_providers.link} target="_blank" rel="noreferrer">
                    View all options on JustWatch
                  </a>
                </p>
              ) : null}
            </section>

            <section className="panel">
              <h4>Release timing</h4>
              {details.media_type === "movie" ? (
                <div className="meta-row">
                  {releaseInfo.theatrical ? (
                    <span>Theatrical: {String(releaseInfo.theatrical)}</span>
                  ) : null}
                  {releaseInfo.digital ? <span>Digital: {String(releaseInfo.digital)}</span> : null}
                </div>
              ) : null}
              {details.media_type === "tv" && releaseInfo.next_episode ? (
                <p>
                  Next episode: {(releaseInfo.next_episode as { name?: string }).name} (
                  {(releaseInfo.next_episode as { days_label?: string }).days_label})
                </p>
              ) : null}
              <p className="countdown">{details.days_label}</p>
            </section>
          </div>

          <section className="panel">
            <h4>Reviews</h4>
            {details.reviews.length ? (
              details.reviews.map((review) => (
                <article className="review" key={`${review.author}-${review.created_at}`}>
                  <strong>
                    {review.author}
                    {review.rating ? ` · ${review.rating}/10` : ""}
                  </strong>
                  <p>{review.content.slice(0, 320)}{review.content.length > 320 ? "…" : ""}</p>
                  {review.url ? (
                    <a href={review.url} target="_blank" rel="noreferrer">
                      Read full review
                    </a>
                  ) : null}
                </article>
              ))
            ) : (
              <p>No TMDB reviews yet.</p>
            )}
          </section>

          <section className="panel">
            <h4>Latest news</h4>
            {details.news.length ? (
              details.news.map((article) => (
                <div className="news-item" key={article.url}>
                  <a href={article.url} target="_blank" rel="noreferrer">
                    <strong>{article.title}</strong>
                  </a>
                  <div className="meta-row">
                    {article.source ? <span>{article.source}</span> : null}
                    {article.published ? <span>{article.published}</span> : null}
                  </div>
                </div>
              ))
            ) : (
              <p>No recent headlines found.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
