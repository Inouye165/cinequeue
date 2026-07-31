import type { MediaItem, WatchlistItem } from "../types";

export interface FormattedReleaseStatus {
  primaryBadge: {
    text: string;
    type: "stream" | "theatre" | "digital" | "season" | "upcoming" | "standard";
    icon: string;
  } | null;
  theatricalText: string | null;
  digitalText: string | null;
  tvPremiereText: string | null;
  tvNextSeasonText: string | null;
  availableMessage: string | null;
}

/**
 * Safely parse ISO date string (YYYY-MM-DD) into Date object in local timezone
 */
export function parseISODate(dateStr?: string | null): Date | null {
  if (!dateStr || typeof dateStr !== "string") return null;
  const parts = dateStr.trim().split("-");
  if (parts.length < 1) return null;
  const year = parseInt(parts[0], 10);
  if (isNaN(year) || year < 1800) return null;
  const month = parts.length > 1 ? parseInt(parts[1], 10) - 1 : 0;
  const day = parts.length > 2 ? parseInt(parts[2], 10) : 1;
  return new Date(year, month, day);
}

/**
 * Format ISO date string to a friendly format e.g. "Aug 4, 2026" or "2026"
 */
export function formatFriendlyDate(dateStr?: string | null): string | null {
  const parsed = parseISODate(dateStr);
  if (!parsed) return dateStr || null;
  
  if (dateStr && dateStr.trim().length === 4) {
    return dateStr;
  }

  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parsed.getMonth()]} ${parsed.getDate()}, ${parsed.getFullYear()}`;
}

/**
 * Returns true if the given date is today or in the past
 */
export function isDatePastOrToday(dateStr?: string | null): boolean {
  const parsed = parseISODate(dateStr);
  if (!parsed) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return parsed.getTime() <= today.getTime();
}

/**
 * Extract formatted release info and availability badges for a MediaItem/WatchlistItem
 */
export function getReleaseInfo(item: MediaItem): FormattedReleaseStatus {
  const watchItem = item as WatchlistItem;
  const providers = item.watch_providers || watchItem.watch_providers;
  const releaseInfo = item.release_info;
  
  const isMovie = item.media_type === "movie";

  // Check providers
  const isFreeStreaming = Boolean(
    providers?.is_free_streaming ||
    watchItem.watch_free_streaming ||
    watchItem.is_free_streaming_alert ||
    (providers?.categories?.streaming && providers.categories.streaming.length > 0) ||
    (providers?.categories?.free && providers.categories.free.length > 0)
  );

  const hasRentOptions = Boolean(providers?.categories?.rent && providers.categories.rent.length > 0);
  const hasBuyOptions = Boolean((providers?.categories?.buy && providers.categories.buy.length > 0) || watchItem.is_on_sale_alert);
  const isRentBuyAvailable = hasRentOptions || hasBuyOptions;

  const isInTheatres = Boolean(
    (providers?.categories?.theatres && providers.categories.theatres.length > 0)
  );

  if (isMovie) {
    const theatricalRaw = item.theatrical_release_date || releaseInfo?.theatrical || item.release_date;
    const digitalRaw = item.digital_release_date || releaseInfo?.digital;

    const theatricalFormatted = theatricalRaw ? formatFriendlyDate(theatricalRaw) : null;
    const digitalFormatted = digitalRaw ? formatFriendlyDate(digitalRaw) : null;

    const theatricalIsPast = theatricalRaw ? isDatePastOrToday(theatricalRaw) : false;
    const digitalIsPast = digitalRaw ? isDatePastOrToday(digitalRaw) : false;

    let primaryBadge: FormattedReleaseStatus["primaryBadge"] = null;
    let availableMessage: string | null = null;

    if (isFreeStreaming) {
      primaryBadge = { text: "Available to Stream", type: "stream", icon: "📺" };
      availableMessage = "Streaming now";
    } else if (isInTheatres || (theatricalIsPast && !digitalIsPast)) {
      primaryBadge = { text: "In Theatres Now", type: "theatre", icon: "🎟️" };
      availableMessage = "Showing in theatres";
    } else if (isRentBuyAvailable || digitalIsPast) {
      const buyPrice = watchItem.buy_current_price;
      const label = buyPrice ? `Rent / Buy (${buyPrice})` : "Available to Rent/Buy";
      primaryBadge = { text: label, type: "digital", icon: "🛒" };
      availableMessage = "Available for digital rental/buy";
    } else if (theatricalRaw && !theatricalIsPast) {
      const daysText = item.days_label || (releaseInfo?.theatrical_days_away !== undefined && releaseInfo.theatrical_days_away !== null ? `In ${releaseInfo.theatrical_days_away} days` : null);
      primaryBadge = {
        text: `In Theatres ${theatricalFormatted ? theatricalFormatted : ""}${daysText ? ` (${daysText})` : ""}`.trim(),
        type: "upcoming",
        icon: "🎬"
      };
    } else if (digitalRaw && !digitalIsPast) {
      primaryBadge = { text: `Digital Release: ${digitalFormatted}`, type: "upcoming", icon: "📅" };
    }

    return {
      primaryBadge,
      theatricalText: theatricalFormatted ? `Theatres: ${theatricalFormatted}` : null,
      digitalText: digitalFormatted ? `Digital/Rent: ${digitalFormatted}` : (isRentBuyAvailable ? "Digital/Rent: Available Now" : null),
      tvPremiereText: null,
      tvNextSeasonText: null,
      availableMessage,
    };
  } else {
    // TV Series
    const premiereRaw = item.release_date;
    const premiereFormatted = premiereRaw ? formatFriendlyDate(premiereRaw) : null;

    const nextSeason = item.next_season;
    const nextEp = releaseInfo?.next_episode;

    let nextSeasonText: string | null = null;
    let tvNextSeasonBadge: FormattedReleaseStatus["primaryBadge"] = null;

    if (nextSeason) {
      const nsDateFormatted = nextSeason.air_date ? formatFriendlyDate(nextSeason.air_date) : null;
      const isNsPast = nextSeason.air_date ? isDatePastOrToday(nextSeason.air_date) : false;
      const cd = nextSeason.days_label;

      if (isNsPast) {
        nextSeasonText = `Next Season: ${nextSeason.name} Released (${nsDateFormatted || "Recently"})`;
        tvNextSeasonBadge = { text: `${nextSeason.name} Available Now`, type: "season", icon: "✨" };
      } else {
        nextSeasonText = `Next Season: ${nextSeason.name}${nsDateFormatted ? ` • ${nsDateFormatted}` : ""}${cd ? ` (${cd})` : ""}`;
        tvNextSeasonBadge = { text: `${nextSeason.name}${cd ? `: ${cd}` : nsDateFormatted ? `: ${nsDateFormatted}` : ""}`, type: "season", icon: "📅" };
      }
    } else if (nextEp && nextEp.air_date) {
      const epDateFormatted = formatFriendlyDate(nextEp.air_date);
      const isEpPast = isDatePastOrToday(nextEp.air_date);
      if (!isEpPast) {
        nextSeasonText = `Next Episode: S${nextEp.season}E${nextEp.episode} (${nextEp.days_label || epDateFormatted})`;
        tvNextSeasonBadge = { text: `S${nextEp.season}E${nextEp.episode}: ${nextEp.days_label || epDateFormatted}`, type: "season", icon: "📡" };
      }
    }

    let primaryBadge: FormattedReleaseStatus["primaryBadge"] = tvNextSeasonBadge;
    let availableMessage: string | null = null;

    if (isFreeStreaming) {
      if (!primaryBadge) {
        primaryBadge = { text: "Available to Stream", type: "stream", icon: "📺" };
      }
      availableMessage = "Available to stream now";
    }

    // User Rule: If next season exists, prioritize next season over original premiere date!
    return {
      primaryBadge,
      theatricalText: null,
      digitalText: null,
      tvPremiereText: nextSeasonText ? null : (premiereFormatted ? `First Air: ${premiereFormatted}` : null),
      tvNextSeasonText: nextSeasonText,
      availableMessage,
    };
  }
}
