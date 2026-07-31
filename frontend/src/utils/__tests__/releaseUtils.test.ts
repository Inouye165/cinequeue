import { describe, expect, it } from "vitest";
import { formatFriendlyDate, getReleaseInfo, isDatePastOrToday, parseISODate } from "../releaseUtils";
import type { MediaItem } from "../../types";

describe("releaseUtils", () => {
  describe("parseISODate & formatFriendlyDate", () => {
    it("parses ISO YYYY-MM-DD date correctly", () => {
      const parsed = parseISODate("2026-07-15");
      expect(parsed).not.toBeNull();
      expect(parsed?.getFullYear()).toBe(2026);
      expect(parsed?.getMonth()).toBe(6); // July is 0-indexed month 6
      expect(parsed?.getDate()).toBe(15);
    });

    it("formats ISO string to friendly text", () => {
      expect(formatFriendlyDate("2026-05-20")).toBe("May 20, 2026");
      expect(formatFriendlyDate("2024-12-01")).toBe("Dec 1, 2024");
      expect(formatFriendlyDate("2025")).toBe("2025");
      expect(formatFriendlyDate(null)).toBeNull();
    });

    it("evaluates past/today dates correctly", () => {
      expect(isDatePastOrToday("2000-01-01")).toBe(true);
      expect(isDatePastOrToday("2099-01-01")).toBe(false);
    });
  });

  describe("getReleaseInfo for Movies", () => {
    it("returns theatrical and digital release dates when present", () => {
      const movie: MediaItem = {
        id: 101,
        media_type: "movie",
        title: "Avatar 3",
        release_date: "2026-12-18",
        theatrical_release_date: "2026-12-18",
        digital_release_date: "2027-03-15",
        release_info: {
          theatrical: "2026-12-18",
          digital: "2027-03-15",
          theatrical_days_away: 140,
        },
      };

      const info = getReleaseInfo(movie);
      expect(info.theatricalText).toBe("Theatres: Dec 18, 2026");
      expect(info.digitalText).toBe("Digital/Rent: Mar 15, 2027");
      expect(info.primaryBadge).not.toBeNull();
      expect(info.primaryBadge?.type).toBe("upcoming");
    });

    it("identifies Available to Stream status for movies", () => {
      const movie: MediaItem = {
        id: 102,
        media_type: "movie",
        title: "Streaming Hit",
        release_date: "2024-01-01",
        watch_providers: {
          is_free_streaming: true,
          categories: {
            streaming: [{ name: "Netflix" }],
          },
        },
      };

      const info = getReleaseInfo(movie);
      expect(info.primaryBadge?.text).toBe("Available to Stream");
      expect(info.primaryBadge?.type).toBe("stream");
    });

    it("identifies Available to Rent/Buy status for released movies", () => {
      const movie: MediaItem = {
        id: 103,
        media_type: "movie",
        title: "Digital Hit",
        release_date: "2023-05-01",
        digital_release_date: "2023-08-01",
        watch_providers: {
          categories: {
            buy: [{ name: "Apple TV", current_price: "$14.99" }],
          },
        },
      };

      const info = getReleaseInfo(movie);
      expect(info.primaryBadge?.text).toContain("Available to Rent/Buy");
      expect(info.primaryBadge?.type).toBe("digital");
    });
  });

  describe("getReleaseInfo for TV Series", () => {
    it("prioritizes next season premiere details over original first air date", () => {
      const show: MediaItem = {
        id: 201,
        media_type: "tv",
        title: "Stranger Things",
        release_date: "2016-07-15",
        next_season: {
          name: "Season 5",
          season_number: 5,
          air_date: "2026-10-31",
          days_label: "In 90 days",
        },
      };

      const info = getReleaseInfo(show);
      expect(info.tvPremiereText).toBeNull(); // Original date hidden in favor of next season date
      expect(info.tvNextSeasonText).toContain("Season 5");
      expect(info.tvNextSeasonText).toContain("Oct 31, 2026");
      expect(info.primaryBadge?.text).toContain("Season 5");
    });

    it("handles TV shows without next season gracefully", () => {
      const show: MediaItem = {
        id: 202,
        media_type: "tv",
        title: "Completed Series",
        release_date: "2010-09-20",
        next_season: null,
      };

      const info = getReleaseInfo(show);
      expect(info.tvPremiereText).toBe("First Air: Sep 20, 2010");
      expect(info.tvNextSeasonText).toBeNull();
    });
  });
});
