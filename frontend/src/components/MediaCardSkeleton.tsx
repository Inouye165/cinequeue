
interface Props {
  count?: number;
}

export function MediaCardSkeleton({ count = 4 }: Props) {
  return (
    <div className="media-grid" aria-label="Loading content" aria-busy="true">
      {Array.from({ length: count }).map((_, index) => (
        <article key={index} className="media-card skeleton-card">
          <div className="poster-wrap skeleton-box" />
          <div className="card-body">
            <div className="skeleton-line skeleton-title" />
            <div className="skeleton-line skeleton-meta" />
            <div className="skeleton-line skeleton-rating" />
            <div className="skeleton-button-row">
              <div className="skeleton-btn" />
              <div className="skeleton-btn" />
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
