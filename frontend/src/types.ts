export type MediaType = "movie" | "tv";

export interface NextSeasonInfo {
  name: string;
  season_number: number;
  air_date?: string | null;
  days_away?: number | null;
  days_label?: string;
}

export interface CastChangeItem {
  character: string;
  actor?: string;
  old_actor?: string;
  new_actor?: string;
}

export interface CastChanges {
  prev_season: number;
  next_season: number;
  returning_with_new_actors: CastChangeItem[];
  written_out: CastChangeItem[];
}

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
  next_season?: NextSeasonInfo | null;
}

export interface WatchlistItem extends MediaItem {
  tmdb_id: number;
  poster_path?: string;
  added_at?: string;
  status?: string;
  is_owned?: boolean;
  owned_format?: "electronic" | "cloud" | "hard_copy" | null;
  watch_free_streaming?: boolean;
  watch_on_sale_buy?: boolean;
  target_rental_price?: number | null;
  is_free_streaming_alert?: boolean;
  is_on_sale_alert?: boolean;
  buy_original_price?: string | null;
  buy_current_price?: string | null;
}

export type PersonalityPreset = "cinephile" | "noir" | "scifi" | "sarcastic" | "custom";

export interface AgentSettings {
  user_id?: string;
  personality_preset: PersonalityPreset;
  custom_prompt?: string;
  location?: string;
  notify_on_login: boolean;
  auto_add_mentioned: boolean;
  track_price_drops: boolean;
  updated_at?: string;
}

export interface ChatAction {
  action: string;
  title: string;
  media_type?: string;
  tmdb_id?: number;
  target_rental_price?: number | null;
}

export interface ChatMessage {
  id?: number | string;
  user_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  actions?: ChatAction[];
  created_at?: string;
}

export interface AgentBriefingUpdate {
  title: string;
  type: string;
  message: string;
  item?: WatchlistItem;
}

export interface AgentBriefing {
  enabled: boolean;
  briefing: string | null;
  updates_count?: number;
  updates?: AgentBriefingUpdate[];
  personality_preset?: string;
}


export interface Provider {
  name: string;
  logo_url?: string | null;
  current_price?: string;
  original_price?: string;
  is_on_sale?: boolean;
}

export interface WatchProviders {
  link?: string;
  categories: {
    streaming?: Provider[];
    free?: Provider[];
    rent?: Provider[];
    buy?: Provider[];
    theatres?: Provider[];
  };
  is_free_streaming?: boolean;
  is_on_sale?: boolean;
  buy_original_price?: string | null;
  buy_current_price?: string | null;
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

export interface Trailer {
  key: string;
  name: string;
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
  trailers?: Trailer[];
  cast_changes?: CastChanges | null;
}
