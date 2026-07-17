import type { MediaItem, WatchlistItem } from "../types";

interface Props {
  item: MediaItem;
  onOpen: (item: MediaItem) => void;
  onAdd?: (item: MediaItem) => void;
  onRemove?: (item: MediaItem) => void;
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
  isOnQueue,
  isFollowing,
  isOwned,
  ownedFormat,
  onMoveToFollowing,
  onMoveToQueue,
}: Props) {
  const watchItem = item as WatchlistItem;
  const isFreeAlert = !isOwned && watchItem.is_free_streaming_alert;
  const isOnSaleAlert = !isOwned && watchItem.is_on_sale_alert;
  const buyPrice = watchItem.buy_current_price;

  const hasAlert = isFreeAlert || isOnSaleAlert;

  return (
    <article className={`media-card ${hasAlert ? "alert-active" : ""}`}>
      <button className="card-hit" onClick={() => onOpen(item)} aria-label={`Open ${item.title}`}>
        <div className="poster-wrap">
          {item.poster_url ? (
            <img src={item.poster_url} alt="" loading="lazy" />
          ) : (
            <div className="poster-placeholder">No poster</div>
          )}
          <span className="badge">{item.media_type === "tv" ? "TV" : "Movie"}</span>
          {isOwned && (
            <span className="badge-owned" title={formatFormat(ownedFormat)}>
              {formatFormat(ownedFormat)}
            </span>
          )}
          {!isOwned && isFollowing && (
            <span className="badge-monitoring" title="Monitoring">
              Monitoring
            </span>
          )}
          
          {(isFreeAlert || isOnSaleAlert) && (
            <div className="card-alerts">
              {isFreeAlert && (
                <span className="card-alert-badge free-streaming">
                  🎉 Now Streaming Free
                </span>
              )}
              {isOnSaleAlert && (
                <span className="card-alert-badge buy-sale">
                  🔥 Price Drop: {buyPrice}
                </span>
              )}
            </div>
          )}
        </div>
      </button>
      <div className="card-body">
        <h3>{item.title}</h3>
        <div className="meta-row">
          {item.media_type === "tv" && item.next_season ? (
            <div className="tv-seasons-info">
              <span className="first-episode-date">
                First Episode: {item.release_date}
              </span>
              <span className="next-season-date">
                Next Season: {item.next_season.name} ({item.next_season.air_date})
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
              {item.release_date && <span>{item.release_date}</span>}
            </>
          )}
          {item.vote_average ? <span className="rating">★ {item.vote_average.toFixed(1)}</span> : null}
        </div>
        {item.overview ? <p>{item.overview.slice(0, 110)}{item.overview.length > 110 ? "…" : ""}</p> : null}
        <div className="card-actions">
          <button className="pill-button" onClick={() => onOpen(item)}>
            Details
          </button>
          {isOwned ? (
            <button className="pill-button" onClick={() => onRemove?.(item)}>
              Remove
            </button>
          ) : isOnQueue ? (
            <>
              <button className="pill-button" onClick={() => onMoveToFollowing?.(item)}>
                Monitor Alerts
              </button>
              <button className="pill-button" onClick={() => onRemove?.(item)}>
                Remove
              </button>
            </>
          ) : isFollowing ? (
            <>
              <button className="pill-button" onClick={() => onMoveToQueue?.(item)}>
                Move to Queue
              </button>
              <button className="pill-button" onClick={() => onRemove?.(item)}>
                Remove
              </button>
            </>
          ) : (
            <button className="pill-button" onClick={() => onAdd?.(item)}>
              + Queue
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
