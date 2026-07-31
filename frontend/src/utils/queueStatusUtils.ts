import type { MediaItem, QueueAvailabilityStatus, WatchlistItem } from "../types";

/**
 * Safely parse ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:mm:ssZ) in local timezone
 */
export function parseLocalDate(dateStr?: string | null): Date | null {
  if (!dateStr || typeof dateStr !== "string") return null;
  const cleaned = dateStr.trim().split("T")[0];
  const parts = cleaned.split("-");
  if (parts.length < 1) return null;
  const year = parseInt(parts[0], 10);
  if (isNaN(year) || year < 1800) return null;
  const month = parts.length > 1 ? parseInt(parts[1], 10) - 1 : 0;
  const day = parts.length > 2 ? parseInt(parts[2], 10) : 1;
  return new Date(year, month, day);
}

/**
 * Returns true if two Date objects fall on the exact same local calendar day (year, month, date)
 */
export function isSameLocalDate(d1: Date, d2: Date): boolean {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

/**
 * Returns true if the target date is on or before the current reference date
 */
export function isDatePastOrToday(dateStr?: string | null, refDate: Date = new Date()): boolean {
  const parsed = parseLocalDate(dateStr);
  if (!parsed) return false;
  const today = new Date(refDate);
  today.setHours(0, 0, 0, 0);
  return parsed.getTime() <= today.getTime();
}

/**
 * Calculate absolute days between reference date and target date
 */
export function getDaysAway(dateStr?: string | null, refDate: Date = new Date()): number | null {
  const parsed = parseLocalDate(dateStr);
  if (!parsed) return null;
  const today = new Date(refDate);
  today.setHours(0, 0, 0, 0);
  const target = new Date(parsed);
  target.setHours(0, 0, 0, 0);
  const diffTime = target.getTime() - today.getTime();
  return Math.round(diffTime / (1000 * 60 * 60 * 24));
}

/**
 * Format ISO date to "MMM D" (e.g. "Aug 26")
 */
export function formatMonthDay(dateStr?: string | null): string | null {
  const parsed = parseLocalDate(dateStr);
  if (!parsed) return dateStr || null;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parsed.getMonth()]} ${parsed.getDate()}`;
}

/**
 * Format ISO date to "MMM D, YYYY" (e.g. "Jul 15, 2026")
 */
export function formatFullDate(dateStr?: string | null): string | null {
  const parsed = parseLocalDate(dateStr);
  if (!parsed) return dateStr || null;
  if (dateStr && dateStr.trim().length === 4) return dateStr;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parsed.getMonth()]} ${parsed.getDate()}, ${parsed.getFullYear()}`;
}

/**
 * Single authoritative Queue Availability Status builder for Movies and Television
 */
export function buildQueueAvailabilityStatus(
  item: MediaItem,
  currentDate: Date = new Date()
): QueueAvailabilityStatus {
  const watchItem = item as WatchlistItem;
  const providers = item.watch_providers || watchItem.watch_providers;
  const releaseInfo = item.release_info;
  const isMovie = item.media_type === "movie";

  const refToday = new Date(currentDate);
  refToday.setHours(0, 0, 0, 0);

  // Streaming / Rent / Buy provider checks
  const isFreeStreaming = Boolean(
    providers?.is_free_streaming ||
    watchItem.watch_free_streaming ||
    watchItem.is_free_streaming_alert ||
    (providers?.categories?.streaming && providers.categories.streaming.length > 0) ||
    (providers?.categories?.free && providers.categories.free.length > 0)
  );

  const hasRentOptions = Boolean(providers?.categories?.rent && providers.categories.rent.length > 0);
  const hasBuyOptions = Boolean(
    (providers?.categories?.buy && providers.categories.buy.length > 0) || watchItem.is_on_sale_alert
  );
  const isRentBuyAvailable = hasRentOptions || hasBuyOptions;

  // -------------------------------------------------------------
  // MOVIE STATUS LOGIC
  // -------------------------------------------------------------
  if (isMovie) {
    const theatricalRaw = item.theatrical_release_date || releaseInfo?.theatrical;
    const digitalRaw = item.digital_release_date || releaseInfo?.digital;
    const primaryReleaseRaw = item.release_date || theatricalRaw || digitalRaw;

    const primaryParsed = parseLocalDate(primaryReleaseRaw);
    const theatricalParsed = parseLocalDate(theatricalRaw);
    const digitalParsed = parseLocalDate(digitalRaw);

    const isReleasingToday =
      (primaryParsed && isSameLocalDate(primaryParsed, refToday)) ||
      (theatricalParsed && isSameLocalDate(theatricalParsed, refToday)) ||
      (digitalParsed && isSameLocalDate(digitalParsed, refToday));

    const isPrimaryPastOrToday = primaryReleaseRaw ? isDatePastOrToday(primaryReleaseRaw, currentDate) : false;
    const isDigitalPastOrToday = digitalRaw ? isDatePastOrToday(digitalRaw, currentDate) : false;

    // A. Releasing Today
    if (isReleasingToday) {
      const formatted = formatFullDate(primaryReleaseRaw || theatricalRaw || digitalRaw);
      return {
        state: "releasing_today",
        primaryText: "Releases today",
        secondaryText: formatted || undefined,
        date: primaryReleaseRaw || undefined,
        accessibilityLabel: `Releases today. ${formatted || ""}`.trim(),
      };
    }

    // B. Released / Available
    if (isPrimaryPastOrToday || isFreeStreaming || isRentBuyAvailable || isDigitalPastOrToday) {
      const releaseDateText = primaryReleaseRaw ? formatFullDate(primaryReleaseRaw) : null;
      if (isFreeStreaming) {
        return {
          state: "available",
          primaryText: "Available now",
          secondaryText: releaseDateText ? `Released ${releaseDateText}` : "Streaming available",
          accessibilityLabel: `Available now. ${releaseDateText ? `Released ${releaseDateText}` : "Streaming available"}`,
        };
      }
      if (isRentBuyAvailable || isDigitalPastOrToday) {
        const buyPrice = watchItem.buy_current_price;
        const buyLabel = buyPrice ? `Rent / buy (${buyPrice})` : "Available to rent/buy";
        return {
          state: "available",
          primaryText: buyLabel,
          secondaryText: releaseDateText ? `Released ${releaseDateText}` : undefined,
          accessibilityLabel: `${buyLabel}. ${releaseDateText ? `Released ${releaseDateText}` : ""}`.trim(),
        };
      }

      // Do NOT assume streamable merely because release date passed!
      return {
        state: "available",
        primaryText: "Released",
        secondaryText: releaseDateText ? `Released ${releaseDateText}` : undefined,
        accessibilityLabel: `Released${releaseDateText ? ` on ${releaseDateText}` : ""}`,
      };
    }

    // C. Upcoming with Known Date
    if (primaryReleaseRaw || theatricalRaw || digitalRaw) {
      const targetDate = theatricalRaw || primaryReleaseRaw || digitalRaw;
      const monthDay = formatMonthDay(targetDate);
      const daysAway = getDaysAway(targetDate, currentDate);
      const daysText = daysAway !== null ? (daysAway === 1 ? "1 day" : `${daysAway} days`) : undefined;

      const primaryLabel = theatricalRaw
        ? `In theaters ${monthDay}`
        : `Releases ${monthDay}`;

      return {
        state: "upcoming",
        primaryText: primaryLabel,
        secondaryText: daysText,
        date: targetDate || undefined,
        accessibilityLabel: `${primaryLabel}${daysText ? `, in ${daysText}` : ""}`,
      };
    }

    // D. Upcoming without a Reliable Date
    return {
      state: "unknown",
      primaryText: "Release date not announced",
      secondaryText: undefined,
      accessibilityLabel: "Release date not announced",
    };
  }

  // -------------------------------------------------------------
  // TELEVISION STATUS LOGIC
  // -------------------------------------------------------------
  const nextEp = item.next_episode_to_air || releaseInfo?.next_episode;
  const lastEp = item.last_episode_to_air || releaseInfo?.last_episode;
  const nextSeason = item.next_season;

  const totalEps = item.number_of_episodes || releaseInfo?.number_of_episodes;
  const totalSeasons = item.number_of_seasons || releaseInfo?.number_of_seasons;
  const showStatus = item.status || releaseInfo?.status;
  const premiereRaw = item.release_date;

  const nextEpAirDate = nextEp?.air_date;
  const nextEpDays = nextEpAirDate ? getDaysAway(nextEpAirDate, currentDate) : null;
  const isNextEpFuture = nextEpAirDate ? !isDatePastOrToday(nextEpAirDate, currentDate) : false;

  const isShowEnded = showStatus === "Ended" || showStatus === "Canceled";

  // A. Next Season Known (Upcoming Season Premiere)
  if (nextSeason && nextSeason.air_date && !isDatePastOrToday(nextSeason.air_date, currentDate)) {
    const nsMonthDay = formatMonthDay(nextSeason.air_date);
    const nsNum = nextSeason.season_number;

    let secText: string | undefined = undefined;
    if (totalSeasons && totalSeasons > 1 && totalEps) {
      secText = `${totalSeasons - 1} season${totalSeasons - 1 > 1 ? "s" : ""} · ${totalEps} episodes released`;
    } else if (totalSeasons && totalSeasons > 1) {
      secText = `${totalSeasons - 1} seasons available`;
    } else if (totalEps) {
      secText = `${totalEps} episodes released`;
    }

    const primaryText = `Season ${nsNum} premieres ${nsMonthDay}`;
    return {
      state: "upcoming",
      primaryText,
      secondaryText: secText,
      seasonNumber: nsNum,
      date: nextSeason.air_date,
      accessibilityLabel: `${primaryText}.${secText ? ` ${secText}` : ""}`,
    };
  }

  // B. Next Episode Known (Partially Released Series)
  if (nextEp && nextEpAirDate && isNextEpFuture) {
    const epNum = nextEp.episode || nextEp.episode_number;
    const seasonNum = nextEp.season || nextEp.season_number;
    const nextEpDateFormatted = formatMonthDay(nextEpAirDate);

    let primaryText: string;
    let availableEpCount: number | undefined = undefined;

    if (epNum && epNum > 1) {
      availableEpCount = epNum - 1;
      // Get current season total if available
      const currentSeasonObj = item.seasons?.find((s) => s.season_number === seasonNum);
      const currentSeasonTotal = currentSeasonObj?.episode_count;

      if (currentSeasonTotal) {
        primaryText = `${availableEpCount} of ${currentSeasonTotal} episodes available`;
      } else {
        primaryText = `${availableEpCount} episodes available`;
      }
    } else {
      primaryText = `Next episode ${nextEpDateFormatted}`;
    }

    const secText = `Next episode ${nextEpDateFormatted}${nextEpDays !== null ? ` (${nextEpDays} days)` : ""}`;

    return {
      state: "partially_available",
      primaryText,
      secondaryText: secText,
      seasonNumber: seasonNum || undefined,
      availableEpisodeCount: availableEpCount,
      nextEpisodeDate: nextEpAirDate,
      accessibilityLabel: `${primaryText}. ${secText}`,
    };
  }

  // C. Future Season Confirmed with Date TBD
  if (
    (showStatus === "Returning Series" || showStatus === "In Production") &&
    (!nextEp || !nextEpAirDate) &&
    (!nextSeason || !nextSeason.air_date)
  ) {
    const nextSeasonNum = (totalSeasons ? totalSeasons + 1 : 2);
    const primaryText = `Season ${nextSeasonNum} confirmed`;
    const secText = "Premiere date TBD";

    return {
      state: "confirmed_tbd",
      primaryText,
      secondaryText: secText,
      seasonNumber: nextSeasonNum,
      accessibilityLabel: `${primaryText}. ${secText}`,
    };
  }

  // D. Series Premieres in Future (No episodes released yet)
  if (premiereRaw && !isDatePastOrToday(premiereRaw, currentDate)) {
    const premiereFormatted = formatMonthDay(premiereRaw);
    const primaryText = `Premieres ${premiereFormatted}`;
    const secText = totalEps ? `Season 1 · ${totalEps} episodes` : "Season 1";

    return {
      state: "upcoming",
      primaryText,
      secondaryText: secText,
      date: premiereRaw,
      accessibilityLabel: `${primaryText}. ${secText}`,
    };
  }

  // E. Complete Series or Ended / Canceled Show
  if (isShowEnded || (totalEps && totalEps > 0 && !nextEp)) {
    let primaryText: string;
    if (totalEps) {
      primaryText = `All ${totalEps} episodes available`;
    } else {
      primaryText = "Complete series available";
    }

    let secText: string | undefined = undefined;
    if (totalSeasons) {
      secText = `${totalSeasons} season${totalSeasons > 1 ? "s" : ""}`;
    } else if (showStatus) {
      secText = showStatus;
    }

    return {
      state: "complete",
      primaryText,
      secondaryText: secText,
      totalEpisodeCount: totalEps || undefined,
      accessibilityLabel: `${primaryText}.${secText ? ` ${secText}` : ""}`,
    };
  }

  // F. Partially Aired Episodes (Last episode in past)
  if (lastEp && lastEp.episode_number) {
    const epCount = lastEp.episode_number;
    const seasonNum = lastEp.season_number || 1;
    const currentSeasonObj = item.seasons?.find((s) => s.season_number === seasonNum);
    const seasonTotal = currentSeasonObj?.episode_count;

    const primaryText = seasonTotal
      ? `${epCount} of ${seasonTotal} episodes available`
      : `${epCount} episodes available`;

    return {
      state: "partially_available",
      primaryText,
      secondaryText: `Season ${seasonNum}`,
      seasonNumber: seasonNum,
      availableEpisodeCount: epCount,
      accessibilityLabel: `${primaryText}. Season ${seasonNum}`,
    };
  }

  // G. Fallback Unknown
  return {
    state: "unknown",
    primaryText: premiereRaw ? `First Air: ${formatFullDate(premiereRaw)}` : "Release schedule unavailable",
    secondaryText: undefined,
    accessibilityLabel: premiereRaw ? `First air date ${formatFullDate(premiereRaw)}` : "Release schedule unavailable",
  };
}

/**
 * Priority rank for default queue sorting
 */
export function getQueueSortRank(state: string): number {
  switch (state) {
    case "available":
      return 1;
    case "partially_available":
      return 2;
    case "releasing_today":
      return 3;
    case "upcoming":
      return 4;
    case "confirmed_tbd":
      return 5;
    case "complete":
      return 6;
    case "unknown":
      return 7;
    default:
      return 8;
  }
}

/**
 * Sorts array of MediaItems according to default queue availability status priority
 */
export function sortQueueItems<T extends MediaItem>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const statusA = buildQueueAvailabilityStatus(a);
    const statusB = buildQueueAvailabilityStatus(b);
    const rankA = getQueueSortRank(statusA.state);
    const rankB = getQueueSortRank(statusB.state);

    if (rankA !== rankB) {
      return rankA - rankB;
    }

    if (statusA.state === "upcoming" && statusB.state === "upcoming") {
      const dateA = statusA.date || a.release_date || "9999-99-99";
      const dateB = statusB.date || b.release_date || "9999-99-99";
      return dateA.localeCompare(dateB);
    }

    return a.title.localeCompare(b.title);
  });
}
