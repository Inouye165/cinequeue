import { useState } from "react";
import type { MediaItem, WatchlistItem } from "../types";
import { StarRating } from "./StarRating";

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
  const watchItem = item as WatchlistItem;
  const isFreeAlert = !isOwned && watchItem.is_free_streaming_alert;
  const isOnSaleAlert = !isOwned && watchItem.is_on_sale_alert;
  const buyPrice = watchItem.buy_current_price;

  const hasAlert = isFreeAlert || isOnSaleAlert;

  return (
    <article className={`media-card ${hasAlert ? "alert-active" : ""}`}>
      <button className="card-hit" onClick={() => onOpen(item)} aria-label={`View details for ${item.title}`}>
        <div className="poster-wrap">
          {item.poster_url && !imageError ? (
            <img
              src={item.poster_url}
              alt=""
              loading="lazy"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="poster-placeholder" aria-label={`Poster unavailable for ${item.title}`}>
              <div className="placeholder-icon" aria-hidden="true">🎬</div>
              <span className="placeholder-title">{item.title}</span>
            </div>
          )}
          <span className="badge">{item.media_type === "tv" ? "TV Series" : "Movie"}</span>
          {isOwned && (
            <span className="badge-owned" title={formatFormat(ownedFormat)}>
              {formatFormat(ownedFormat)}
            </span>
          )}
          {!isOwned && isFollowing && (
            <span className="badge-monitoring" title="Monitoring price & release alerts">
              Monitoring
            </span>
          )}

          {(isFreeAlert || isOnSaleAlert) && (
            <div className="card-alerts">
              {isFreeAlert && (
                <span className="card-alert-badge free-streaming">
                  🎉 Free to Stream
                </span>
              )}
              {isOnSaleAlert && (
                <span className="card-alert-badge buy-sale">
                  🔥 Sale: {buyPrice}
                </span>
              )}
            </div>
          )}
        </div>
      </button>
      <div className="card-body">
        <h3 title={item.title}>{item.title}</h3>
        <div className="meta-row">
          {item.media_type === "tv" && item.next_season ? (
            <div className="tv-seasons-info">
              {item.release_date && <span className="first-episode-date">First Air: {item.release_date}</span>}
              <span className="next-season-date">
                Next Season: {item.next_season.name}
                {item.next_season.days_label && (
                  <span className="countdown" style={{ marginLeft: "6px" }}>
                    {item.next_season.days_label}
                  </span>
                )}
              </span>
            </div>
          ) : (
            <>
              {item.days_label && <span className="countdown">{item.days_label}</span>}
              {item.release_date && <span className="release-year">{item.release_date.slice(0, 4)}</span>}
            </>
          )}
          {item.vote_average ? <span className="rating" aria-label={`Rating ${item.vote_average.toFixed(1)} out of 10`}>★ {item.vote_average.toFixed(1)}</span> : null}
        </div>
        {item.overview ? <p className="overview-snippet">{item.overview}</p> : null}
        <div className="card-user-rating">
          <span className="rating-label">Your Rating:</span>
          <StarRating
            rating={watchItem.user_rating !== undefined ? watchItem.user_rating : userRating}
            onRate={(rating) => onRate?.(item, rating)}
            size="sm"
          />
        </div>
        <div className="card-actions">
          <button className="pill-button secondary" onClick={() => onOpen(item)}>
            Details
          </button>
          {isOwned ? (
            <button className="pill-button danger" onClick={() => onRemove?.(item)} aria-label={`Remove ${item.title} from library`}>
              Remove
            </button>
          ) : isOnQueue ? (
            <>
              <button className="pill-button secondary" onClick={() => onMoveToFollowing?.(item)} aria-label={`Monitor alerts for ${item.title}`}>
                Monitor
              </button>
              <button className="pill-button danger" onClick={() => onRemove?.(item)} aria-label={`Remove ${item.title} from queue`}>
                Remove
              </button>
            </>
          ) : isFollowing ? (
            <>
              <button className="pill-button primary" onClick={() => onMoveToQueue?.(item)} aria-label={`Move ${item.title} to queue`}>
                Move to Queue
              </button>
              <button className="pill-button danger" onClick={() => onRemove?.(item)} aria-label={`Remove ${item.title} from monitoring`}>
                Remove
              </button>
            </>
          ) : (
            <button className="pill-button primary" onClick={() => onAdd?.(item)} aria-label={`Add ${item.title} to queue`}>
              + Queue
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
