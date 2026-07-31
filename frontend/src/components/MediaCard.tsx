import { useState, useRef, useEffect } from "react";
import type { MediaItem, WatchlistItem } from "../types";
import { StarRating } from "./StarRating";
import { formatPosterUrl } from "../utils/mediaUtils";
import { buildQueueAvailabilityStatus } from "../utils/queueStatusUtils";

interface Props {
  item: MediaItem;
  onOpen: (item: MediaItem) => void;
  onAdd?: (item: MediaItem) => void;
  onRemove?: (item: MediaItem) => void;
  onRate?: (item: MediaItem, rating: number) => void;
  userRating?: number | null;
  isOnWatchlist?: boolean;
  isOnQueue?: boolean;
  isFollowing?: boolean;
  isOwned?: boolean;
  ownedFormat?: "electronic" | "cloud" | "hard_copy" | null;
  onMoveToFollowing?: (item: MediaItem) => void;
  onMoveToQueue?: (item: MediaItem) => void;
}

function formatFormat(format?: string | null) {
  if (format === "electronic") return "Electronic";
  if (format === "cloud") return "Cloud";
  if (format === "hard_copy") return "Hard Copy";
  return "Owned";
}

function getStateIcon(state: string): string {
  switch (state) {
    case "available":
      return "✓";
    case "partially_available":
      return "📊";
    case "releasing_today":
      return "🎉";
    case "upcoming":
      return "📅";
    case "confirmed_tbd":
      return "⏳";
    default:
      return "ℹ️";
  }
}

export function MediaCard({
  item,
  onOpen,
  onAdd,
  onRemove,
  onRate,
  userRating,
  isOnQueue,
  isFollowing,
  isOwned,
  ownedFormat,
  onMoveToFollowing,
  onMoveToQueue,
}: Props) {
  const [imageError, setImageError] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const watchItem = item as WatchlistItem;
  const rawPoster = item.poster_url || watchItem.poster_path;
  const posterUrl = formatPosterUrl(rawPoster);

  const status = buildQueueAvailabilityStatus(item);

  // Close overflow menu on outside click or Escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  const yearStr = item.release_date ? item.release_date.slice(0, 4) : null;
  const mediaTypeLabel = item.media_type === "tv" ? "TV series" : "Movie";
  const seasonStr = status.seasonNumber ? `Season ${status.seasonNumber}` : null;
  const metaText = [mediaTypeLabel, seasonStr || yearStr].filter(Boolean).join(" · ");

  return (
    <article className="media-card" aria-label={`${item.title}, ${status.accessibilityLabel}`}>
      {/* 1. Poster Area */}
      <button
        className="card-hit"
        onClick={() => onOpen(item)}
        aria-label={`Open details for ${item.title}`}
      >
        <div className="poster-wrap">
          {posterUrl && !imageError ? (
            <img
              src={posterUrl}
              alt={`Poster for ${item.title}`}
              loading="lazy"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="poster-placeholder" aria-label={`Poster unavailable for ${item.title}`}>
              <div className="placeholder-icon" aria-hidden="true">🎬</div>
              <span className="placeholder-title">{item.title}</span>
            </div>
          )}
          <span className="badge">{item.media_type === "tv" ? "TV" : "Movie"}</span>
          {isOwned && (
            <span className="badge-owned" title={formatFormat(ownedFormat)}>
              {formatFormat(ownedFormat)}
            </span>
          )}
        </div>
      </button>

      {/* 2. Content Area */}
      <div className="card-body">
        {/* Single Authoritative Availability Section Directly Below Poster */}
        <div className={`availability-block state-${status.state}`} aria-label={status.accessibilityLabel}>
          <div className="availability-primary">
            <span className="status-state-icon" aria-hidden="true">
              {getStateIcon(status.state)}
            </span>
            <span className="status-primary-text">{status.primaryText}</span>
          </div>
          {status.secondaryText && (
            <div className="availability-secondary">{status.secondaryText}</div>
          )}
        </div>

        {/* 3. Title */}
        <h3 title={item.title} className="card-title" onClick={() => onOpen(item)}>
          {item.title}
        </h3>

        {/* 4. Metadata Row */}
        <div className="card-meta-row">
          <span className="meta-info">{metaText}</span>
          {item.vote_average ? (
            <span className="rating" aria-label={`Rating ${item.vote_average.toFixed(1)} out of 10`}>
              ★ {item.vote_average.toFixed(1)}
            </span>
          ) : null}
        </div>

        {/* 5. Optional Line-Clamped Overview */}
        {item.overview ? <p className="overview-snippet">{item.overview}</p> : null}

        {/* Star Rating Control */}
        <div className="card-user-rating">
          <StarRating
            rating={watchItem.user_rating !== undefined ? watchItem.user_rating : userRating}
            onRate={(rating) => onRate?.(item, rating)}
            size="sm"
          />
        </div>

        {/* 6. Restrained Action Area: 1 Primary Button + Compact Overflow Menu */}
        <div className="card-actions-row">
          <button
            className="pill-button primary action-btn-primary"
            onClick={() => onOpen(item)}
            aria-label={`View details for ${item.title}`}
          >
            View details
          </button>

          {/* Kebab Overflow Menu */}
          <div className="overflow-menu-container" ref={menuRef}>
            <button
              className="icon-button overflow-menu-btn"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label={`Options for ${item.title}`}
              aria-expanded={menuOpen}
              type="button"
            >
              ⋮
            </button>

            {menuOpen && (
              <div className="overflow-dropdown-menu" role="menu">
                {!isOnQueue && !isFollowing && !isOwned && onAdd && (
                  <button
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onAdd(item);
                    }}
                  >
                    + Add to Queue
                  </button>
                )}
                {isOnQueue && onMoveToFollowing && (
                  <button
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onMoveToFollowing(item);
                    }}
                  >
                    Monitor Alerts
                  </button>
                )}
                {isFollowing && onMoveToQueue && (
                  <button
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onMoveToQueue(item);
                    }}
                  >
                    Move to Queue
                  </button>
                )}
                {onRemove && (
                  <button
                    className="dropdown-item danger"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onRemove(item);
                    }}
                  >
                    Remove
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
