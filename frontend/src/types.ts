export type MediaType = "movie" | "tv";

export type QueueAvailabilityState =
  | "available"
  | "partially_available"
  | "upcoming"
  | "releasing_today"
  | "confirmed_tbd"
  | "complete"
  | "unknown";

export interface QueueAvailabilityStatus {
  state: QueueAvailabilityState;
  primaryText: string;
  secondaryText?: string;
  tertiaryText?: string;
  date?: string;
  availableEpisodeCount?: number;
  totalEpisodeCount?: number;
  nextEpisodeDate?: string;
  seasonNumber?: number;
  accessibilityLabel: string;
}

export interface NextSeasonInfo {
  name: string;
  season_number: number;
  air_date?: string | null;
  days_away?: number | null;
  days_label?: string;
}

export interface TVEpisodeDetails {
  name?: string | null;
  season?: number | null;
  season_number?: number | null;
  episode?: number | null;
  episode_number?: number | null;
  air_date?: string | null;
  days_away?: number | null;
  days_label?: string | null;
}

export interface ReleaseInfo {
  theatrical?: string | null;
  digital?: string | null;
  theatrical_days_away?: number | null;
  digital_days_away?: number | null;
  next_episode?: TVEpisodeDetails | null;
  last_episode?: TVEpisodeDetails | null;
  number_of_episodes?: number | null;
  number_of_seasons?: number | null;
  status?: string | null;
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
  poster_path?: string | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
  release_date?: string | null;
  theatrical_release_date?: string | null;
  digital_release_date?: string | null;
  days_away?: number | null;
  days_label?: string;
  vote_average?: number;
  vote_count?: number;
  popularity?: number;
  next_season?: NextSeasonInfo | null;
  release_info?: ReleaseInfo | null;
  watch_providers?: WatchProviders | null;
  user_rating?: number | null;
  number_of_episodes?: number | null;
  number_of_seasons?: number | null;
  status?: string | null;
  next_episode_to_air?: TVEpisodeDetails | null;
  last_episode_to_air?: TVEpisodeDetails | null;
  seasons?: Array<{
    id?: number;
    name?: string;
    season_number?: number;
    episode_count?: number;
    air_date?: string | null;
  }> | null;
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

export interface RatedMovie {
  id?: number | string;
  user_id?: string;
  media_type: MediaType;
  tmdb_id: number;
  title: string;
  poster_path?: string | null;
  poster_url?: string | null;
  release_date?: string | null;
  rating: number;
  rated_at?: string;
  updated_at?: string;
  rated_ago?: string;
  overview?: string;
}

export interface ChatAction {
  action: string;
  title?: string;
  media_type?: string;
  tmdb_id?: number;
  rating?: number;
  status?: string;
  is_owned?: boolean;
  target_rental_price?: number | null;
  movies?: RatedMovie[];
  query?: string;
  results?: RatedMovie[];
  poster_url?: string | null;
  release_date?: string | null;
  availability_type?: "free" | "rent" | "buy";
  provider_name?: string;
  price?: string;
  details_text?: string;
  overview?: string;
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
  summary?: string;
  category?: string;
  published_at?: string;
  item?: WatchlistItem;
}

export interface AgentBriefing {
  enabled: boolean;
  briefing: string | null;
  updates_count?: number;
  updates?: AgentBriefingUpdate[];
  personality_preset?: string;
}

export interface AgentLogEntry {
  log_id: string;
  event_type: string;
  timestamp: string;
  user_id: string;
  session_id?: string | null;
  model_requested?: string | null;
  model_used?: string | null;
  gemini_called: boolean;
  fallback_used: boolean;
  fallback_reason?: string | null;
  selection_summary?: string;
  sanitized_prompt?: string;
  raw_model_response?: string;
  final_response?: string;
  request_duration_ms?: number;
  selected_candidates?: any[];
  excluded_candidates?: any[];
  cooldowns_applied?: string[];
  prompt_char_count?: number;
  prompt_token_count?: number;
  response_char_count?: number;
  response_token_count?: number;
  total_token_count?: number;
  estimated_cost_usd?: number;
  daily_cache_key?: string | null;
  daily_cache_result?: string | null;
  served_from?: string | null;
  content_origin?: string | null;
  result_source?: string | null;
  user_timezone?: string | null;
  configured_user_timezone?: string | null;
  resolved_user_timezone?: string | null;
  timezone_resolution_source?: string | null;
  timezone_resolution_error?: string | null;
  resolved_local_date?: string | null;
  attempt_number?: number;
  is_fallback_attempt?: boolean;
  http_status?: number | null;
  success?: boolean;
  error_type?: string | null;
  gemini_request_id?: string | null;
}

export interface AgentLogsResponse {
  total: number;
  limit: number;
  logs: AgentLogEntry[];
  summary: {
    total_calls: number;
    avg_duration_ms: number;
    fallback_count: number;
    success_rate_percent: number;
  };
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
