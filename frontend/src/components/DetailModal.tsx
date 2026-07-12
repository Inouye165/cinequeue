import type { MediaDetails } from "../types";

interface Props {
  details: MediaDetails;
  isOnWatchlist: boolean;
  onClose: () => void;
  onAdd: () => void;
  onRemove: () => void;
}

export function DetailModal({ details, isOnWatchlist, onClose, onAdd, onRemove }: Props) {
  const providers = details.watch_providers?.categories ?? {};
  const releaseInfo = details.release_info as Record<string, string | number | null | undefined>;

  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <button className="icon-button close-button" onClick={onClose}>
          Close
        </button>
        <div
          className="detail-hero"
          style={
            details.backdrop_url
              ? { backgroundImage: `url(${details.backdrop_url})` }
              : undefined
          }
        >
          <div className="detail-hero-content">
            {details.poster_url ? <img src={details.poster_url} alt="" /> : null}
            <div>
              <p>{details.media_type === "tv" ? "TV Series" : "Movie"}</p>
              <h2>{details.title}</h2>
              {details.tagline ? <p>{details.tagline}</p> : null}
              <div className="meta-row">
                <span className="countdown">{details.days_label}</span>
                {details.release_date ? <span>{details.release_date}</span> : null}
                {details.vote_average ? <span className="rating">★ {details.vote_average.toFixed(1)}</span> : null}
                {details.runtime_minutes ? <span>{details.runtime_minutes} min</span> : null}
              </div>
              <div className="chip-list" style={{ marginTop: 12 }}>
                {details.genres?.map((genre) => (
                  <span className="chip" key={genre}>
                    {genre}
                  </span>
                ))}
              </div>
              <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
                {isOnWatchlist ? (
                  <button className="pill-button" onClick={onRemove}>
                    Remove from queue
                  </button>
                ) : (
                  <button className="pill-button" onClick={onAdd}>
                    Add to queue
                  </button>
                )}
                {details.homepage ? (
                  <a className="pill-button" href={details.homepage} target="_blank" rel="noreferrer">
                    Official site
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <div className="detail-content">
          {details.overview ? <p>{details.overview}</p> : null}

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
              {providers.streaming?.length ? (
                <>
                  <strong>Streaming</strong>
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
                      </span>
                    ))}
                  </div>
                </>
              ) : null}
              {!providers.streaming?.length &&
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
