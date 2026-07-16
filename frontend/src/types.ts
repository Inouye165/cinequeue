export type MediaType = "movie" | "tv";

export interface MediaItem {
  id: number;
  media_type: MediaType;
  title: string;
  overview?: string;
  poster_url?: string | null;
  backdrop_url?: string | null;
  release_date?: string | null;
  days_away?: number | null;
  days_label?: string;
  vote_average?: number;
  vote_count?: number;
  popularity?: number;
}

export interface WatchlistItem extends MediaItem {
  tmdb_id: number;
  poster_path?: string;
  added_at?: string;
  status?: string;
  is_owned?: boolean;
  owned_format?: "electronic" | "cloud" | "hard_copy" | null;
}

export interface Provider {
  name: string;
  logo_url?: string | null;
}

export interface WatchProviders {
  link?: string;
  categories: {
    streaming?: Provider[];
    rent?: Provider[];
    buy?: Provider[];
    theatres?: Provider[];
  };
}

export interface Review {
  author: string;
  rating?: number | null;
  content: string;
  url?: string;
  created_at?: string;
}

export interface NewsArticle {
  title: string;
  url: string;
  published?: string;
  source?: string | null;
}

export interface MediaDetails extends MediaItem {
  tagline?: string;
  genres?: string[];
  runtime_minutes?: number;
  status?: string;
  homepage?: string;
  watch_providers: WatchProviders;
  reviews: Review[];
  release_info: Record<string, unknown>;
  news: NewsArticle[];
}
