import type { MediaItem } from "../types";

interface Props {
  item: MediaItem;
  onOpen: (item: MediaItem) => void;
  onAdd?: (item: MediaItem) => void;
  onRemove?: (item: MediaItem) => void;
  isOnWatchlist?: boolean;
  isOwned?: boolean;
  ownedFormat?: "electronic" | "cloud" | "hard_copy" | null;
}

function formatFormat(format?: string | null) {
  if (format === "electronic") return "Electronic";
  if (format === "cloud") return "Cloud";
  if (format === "hard_copy") return "Hard Copy";
  return "Owned";
}

export function MediaCard({ item, onOpen, onAdd, onRemove, isOnWatchlist, isOwned, ownedFormat }: Props) {
  const showRemoveButton = isOnWatchlist || isOwned;

  return (
    <article className="media-card">
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
        </div>
      </button>
      <div className="card-body">
        <h3>{item.title}</h3>
        <div className="meta-row">
          {item.days_label && <span className="countdown">{item.days_label}</span>}
          {item.release_date && <span>{item.release_date}</span>}
          {item.vote_average ? <span className="rating">★ {item.vote_average.toFixed(1)}</span> : null}
        </div>
        {item.overview ? <p>{item.overview.slice(0, 110)}{item.overview.length > 110 ? "…" : ""}</p> : null}
        <div className="card-actions">
          <button className="pill-button" onClick={() => onOpen(item)}>
            Details
          </button>
          {showRemoveButton ? (
            <button className="pill-button" onClick={() => onRemove?.(item)}>
              Remove
            </button>
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
