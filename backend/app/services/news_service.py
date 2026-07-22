"""Entertainment news service for discovering, classifying, deduplicating, clustering, and ranking news items."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
import hashlib
import logging
import re
import time
from typing import Any

from app.services.tmdb import TmdbClient

logger = logging.getLogger(__name__)


class NewsCategory:
    RELEASE_DATE_ANNOUNCED = "release_date_announced"
    RELEASE_DATE_CHANGED = "release_date_changed"
    STREAMING_AVAILABILITY_ANNOUNCED = "streaming_availability_announced"
    TRAILER_RELEASED = "trailer_released"
    CASTING_ANNOUNCEMENT = "casting_announcement"
    PRODUCTION_STARTED = "production_started"
    PRODUCTION_DELAYED = "production_delayed"
    PRODUCTION_COMPLETED = "production_completed"
    RENEWAL = "renewal"
    CANCELLATION = "cancellation"
    NEW_SEASON_ANNOUNCEMENT = "new_season_announcement"
    SEQUEL_ANNOUNCEMENT = "sequel_announcement"
    DIRECTOR_WRITER_ANNOUNCEMENT = "director_writer_announcement"
    OFFICIAL_SYNOPSIS_FOOTAGE = "official_synopsis_footage"
    BOX_OFFICE_MILESTONE = "box_office_milestone"
    REVIEW_RECEPTION_UPDATE = "review_reception_update"
    RUMOR_UNCONFIRMED = "rumor_unconfirmed"


class NewsVerification:
    OFFICIAL = "official"
    CONFIRMED = "confirmed"
    REPORTED = "reported"
    RUMOR = "rumor"


@dataclass
class NewsArticleData:
    headline: str
    source: str
    url: str
    published_at: str
    first_discovered_at: str
    last_checked_at: str
    related_title: str
    title_id: str
    category: str
    verification: str
    summary: str
    normalized_url: str
    content_fingerprint: str
    story_cluster_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_url(url: str) -> str:
    """Normalize article URL by stripping tracking parameters."""
    clean = re.sub(r'\?.*$', '', url.strip().lower())
    clean = re.sub(r'^https?://(www\.)?', '', clean)
    return clean.rstrip('/')


def compute_content_fingerprint(text: str) -> str:
    """Generate SHA256 content fingerprint for deduplication."""
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def classify_news_item(headline: str, source_name: str = "") -> tuple[str, str]:
    """Classify news headline into category and verification status."""
    hl = headline.lower()
    src = source_name.lower()

    # Verification status
    if any(w in hl for w in ["officially", "confirmed", "announces", "studio confirms", "netflix announces", "hbo confirms", "disney confirms"]):
        verification = NewsVerification.OFFICIAL
    elif any(w in src for w in ["variety", "deadline", "hollywood reporter", "thr", "empire"]):
        verification = NewsVerification.CONFIRMED
    elif "rumor" in hl or "unconfirmed" in hl or "reportedly" in hl or "alleged" in hl:
        verification = NewsVerification.RUMOR
    else:
        verification = NewsVerification.REPORTED

    # Category classification
    if "trailer" in hl or "teaser" in hl or "first look video" in hl:
        category = NewsCategory.TRAILER_RELEASED
    elif "release date" in hl or "premieres" in hl or "arrives on" in hl:
        category = NewsCategory.RELEASE_DATE_ANNOUNCED
    elif "delayed" in hl or "postponed" in hl or "pushed back" in hl:
        category = NewsCategory.RELEASE_DATE_CHANGED
    elif "filming" in hl or "production begins" in hl or "production started" in hl or "began shooting" in hl:
        category = NewsCategory.PRODUCTION_STARTED
    elif "wrapped" in hl or "filming completes" in hl or "production wrapped" in hl:
        category = NewsCategory.PRODUCTION_COMPLETED
    elif "renewed" in hl or "season 2 confirmed" in hl or "season 3 confirmed" in hl:
        category = NewsCategory.RENEWAL
    elif "canceled" in hl or "cancelled" in hl or "axed" in hl or "not returning" in hl:
        category = NewsCategory.CANCELLATION
    elif "cast" in hl or "joins" in hl or "stars in" in hl or "to play" in hl:
        category = NewsCategory.CASTING_ANNOUNCEMENT
    elif "sequel" in hl or "spin-off" in hl or "spinoff" in hl:
        category = NewsCategory.SEQUEL_ANNOUNCEMENT
    elif "streaming on" in hl or "available on" in hl or "drops on" in hl:
        category = NewsCategory.STREAMING_AVAILABILITY_ANNOUNCED
    elif verification == NewsVerification.RUMOR:
        category = NewsCategory.RUMOR_UNCONFIRMED
    else:
        category = NewsCategory.OFFICIAL_SYNOPSIS_FOOTAGE

    return category, verification


def generate_story_cluster_id(title_id: str, category: str, content_fp: str) -> str:
    """Generate deterministic story cluster identifier for deduplication."""
    clean_title = re.sub(r'[^a-zA-Z0-9_]', '', title_id.lower())
    return f"cluster:{clean_title}:{category}:{content_fp[:8]}"


class NewsProvider(ABC):
    @abstractmethod
    async def fetch_news_for_title(self, title: str, title_id: str) -> list[NewsArticleData]:
        ...


class TmdbEntertainmentNewsProvider(NewsProvider):
    def __init__(self, tmdb: TmdbClient | None) -> None:
        self.tmdb = tmdb

    async def fetch_news_for_title(self, title: str, title_id: str) -> list[NewsArticleData]:
        if not self.tmdb or not title:
            return []

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        results = []

        try:
            articles = await self.tmdb.get_news(title)
            for art in articles:
                headline = art.get("title", "").strip()
                if not headline:
                    continue

                url = art.get("link", "")
                source = art.get("source", "Entertainment News")
                published_at = art.get("published") or now_iso
                norm_url = normalize_url(url) if url else f"no-url-{compute_content_fingerprint(headline)}"
                content_fp = compute_content_fingerprint(headline)
                category, verification = classify_news_item(headline, source)
                cluster_id = generate_story_cluster_id(title_id, category, content_fp)

                results.append(NewsArticleData(
                    headline=headline,
                    source=source,
                    url=url,
                    published_at=published_at,
                    first_discovered_at=now_iso,
                    last_checked_at=now_iso,
                    related_title=title,
                    title_id=title_id,
                    category=category,
                    verification=verification,
                    summary=headline,
                    normalized_url=norm_url,
                    content_fingerprint=content_fp,
                    story_cluster_id=cluster_id,
                ))
        except Exception as e:
            logger.warning(f"Error fetching news for '{title}': {e}")

        return results


def cluster_news_stories(articles: list[NewsArticleData]) -> list[dict[str, Any]]:
    """Group articles describing the same underlying event into a single story cluster.
    
    Retains the strongest/most authoritative source as the primary source while
    preserving supporting sources.
    """
    clusters: dict[str, list[NewsArticleData]] = {}

    for art in articles:
        c_id = art.story_cluster_id
        if c_id not in clusters:
            clusters[c_id] = []
        clusters[c_id].append(art)

    verification_priority = {
        NewsVerification.OFFICIAL: 1,
        NewsVerification.CONFIRMED: 2,
        NewsVerification.REPORTED: 3,
        NewsVerification.RUMOR: 4,
    }

    clustered_results = []
    for cluster_id, items in clusters.items():
        # Sort items in cluster by verification priority and recency
        items.sort(key=lambda x: (verification_priority.get(x.verification, 3), x.published_at), reverse=False)
        primary = items[0]
        supporting_sources = [it.source for it in items[1:] if it.source != primary.source]

        clustered_results.append({
            "story_cluster_id": cluster_id,
            "primary_article": primary.to_dict(),
            "supporting_sources": supporting_sources,
            "total_articles": len(items),
            "headline": primary.headline,
            "source": primary.source,
            "url": primary.url,
            "category": primary.category,
            "verification": primary.verification,
            "related_title": primary.related_title,
            "title_id": primary.title_id,
            "content_fingerprint": primary.content_fingerprint,
            "published_at": primary.published_at,
            "first_discovered_at": primary.first_discovered_at,
            "summary": primary.summary,
        })

    return clustered_results


def rank_briefing_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank unseen and materially changed briefing candidates.
    
    Urgency scale (1 = top priority, 5 = lower priority):
    1: Available now, imminent release (<=3 days), official renewal/cancellation
    2: Major news (official production started, trailer released, price drop, memory recall)
    3: Upcoming release (4-14 days), casting announcement
    4: General news / updates
    """
    urgency_map = {
        "newly_available": 1,
        "imminent_release": 1,
        NewsCategory.CANCELLATION: 1,
        NewsCategory.RENEWAL: 1,
        NewsCategory.RELEASE_DATE_CHANGED: 1,
        NewsCategory.RELEASE_DATE_ANNOUNCED: 1,
        "price_drop": 2,
        "free_streaming": 2,
        "memory_recall": 2,
        NewsCategory.PRODUCTION_STARTED: 2,
        NewsCategory.TRAILER_RELEASED: 2,
        NewsCategory.STREAMING_AVAILABILITY_ANNOUNCED: 2,
        "upcoming_release": 3,
        NewsCategory.CASTING_ANNOUNCEMENT: 3,
        NewsCategory.PRODUCTION_COMPLETED: 3,
    }

    for c in candidates:
        cat = c.get("category") or c.get("type", "")
        base_urgency = urgency_map.get(cat, c.get("urgency", 4))

        # Verification bonus: official/confirmed outranks rumors
        verif = c.get("verification")
        if verif == NewsVerification.RUMOR:
            base_urgency += 1

        c["importance_score"] = base_urgency

    # Sort candidates by importance score (ascending), newness to user, and recency
    candidates.sort(key=lambda x: (
        x.get("importance_score", 4),
        not x.get("new_to_user", True),
        x.get("published_at", "")
    ))

    return candidates
