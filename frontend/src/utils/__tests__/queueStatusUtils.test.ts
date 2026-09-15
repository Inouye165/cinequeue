import { describe, expect, it } from "vitest";
import { buildQueueAvailabilityStatus, formatFullDate, formatMonthDay, isSameLocalDate, parseLocalDate, sortQueueItems } from "../queueStatusUtils";
import type { MediaItem } from "../../types";

describe("queueStatusUtils", () => {
  const refDate = new Date("2026-08-01T12:00:00Z");

  describe("Date Parsing & Formatting", () => {
    it("parses local ISO date strings correctly", () => {
      const parsed = parseLocalDate("2026-08-15");
      expect(parsed).not.toBeNull();
      expect(parsed?.getFullYear()).toBe(2026);
      expect(parsed?.getMonth()).toBe(7); // August is month index 7
      expect(parsed?.getDate()).toBe(15);
    });

    it("identifies same local dates", () => {
      const d1 = new Date(2026, 7, 1);
      const d2 = new Date(2026, 7, 1, 15, 30);
      expect(isSameLocalDate(d1, d2)).toBe(true);
    });

    it("formats month day strings correctly", () => {
      expect(formatMonthDay("2026-08-26")).toBe("Aug 26");
      expect(formatFullDate("2026-07-15")).toBe("Jul 15, 2026");
      expect(formatFullDate(null)).toBeNull();
    });
  });

  describe("Movie Availability Status Logic", () => {
    it("handles released movies with streaming availability", () => {
      const movie: MediaItem = {
        id: 1,
        media_type: "movie",
        title: "The Odyssey",
        release_date: "2026-07-15",
        watch_providers: {
          is_free_streaming: true,
          categories: {},
        },
      };

      const status = buildQueueAvailabilityStatus(movie, refDate);
      expect(status.state).toBe("available");
      expect(status.primaryText).toBe("Available now");
      expect(status.secondaryText).toBe("Released Jul 15, 2026");
    });

    it("handles released movies without stream verification (does not assume streamable)", () => {
      const movie: MediaItem = {
        id: 2,
        media_type: "movie",
        title: "Old Movie",
        release_date: "2025-05-10",
      };

      const status = buildQueueAvailabilityStatus(movie, refDate);
      expect(status.state).toBe("available");
      expect(status.primaryText).toBe("Released");
      expect(status.secondaryText).toBe("Released May 10, 2025");
    });

    it("handles movies releasing today", () => {
      const movie: MediaItem = {
        id: 3,
        media_type: "movie",
        title: "Today Blockbuster",
        release_date: "2026-08-01",
      };

      const status = buildQueueAvailabilityStatus(movie, refDate);
      expect(status.state).toBe("releasing_today");
      expect(status.primaryText).toBe("Releases today");
      expect(status.secondaryText).toBe("Aug 1, 2026");
    });

    it("handles upcoming movies with known theatrical date", () => {
      const movie: MediaItem = {
        id: 4,
        media_type: "movie",
        title: "The Dog Stars",
        theatrical_release_date: "2026-08-26",
      };

      const status = buildQueueAvailabilityStatus(movie, refDate);
      expect(status.state).toBe("upcoming");
      expect(status.primaryText).toBe("In theaters Aug 26");
      expect(status.secondaryText).toBe("25 days");
    });

    it("handles upcoming movies with missing release date", () => {
      const movie: MediaItem = {
        id: 5,
        media_type: "movie",
        title: "Unknown Movie",
        release_date: null,
      };

      const status = buildQueueAvailabilityStatus(movie, refDate);
      expect(status.state).toBe("unknown");
      expect(status.primaryText).toBe("Release date not announced");
      expect(status.secondaryText).toBeUndefined();
    });
  });

  describe("Television Availability Status Logic", () => {
    it("handles partially released TV series with next episode date (4 of 12)", () => {
      const show: MediaItem = {
        id: 10,
        media_type: "tv",
        title: "Example Series",
        number_of_episodes: 12,
        number_of_seasons: 2,
        next_episode_to_air: {
          season_number: 2,
          episode_number: 5,
          air_date: "2026-08-07",
        },
        seasons: [
          { season_number: 2, episode_count: 12 },
        ],
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("partially_available");
      expect(status.primaryText).toBe("4 of 12 episodes available");
      expect(status.secondaryText).toContain("Next episode Aug 7");
    });

    it("handles completed TV series (all episodes available)", () => {
      const show: MediaItem = {
        id: 11,
        media_type: "tv",
        title: "Complete Show",
        number_of_episodes: 10,
        number_of_seasons: 1,
        status: "Ended",
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("complete");
      expect(status.primaryText).toBe("All 10 episodes available");
      expect(status.secondaryText).toBe("1 season");
    });

    it("handles unreleased TV series with known premiere date", () => {
      const show: MediaItem = {
        id: 12,
        media_type: "tv",
        title: "New Show",
        release_date: "2026-08-14",
        number_of_episodes: 12,
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("upcoming");
      expect(status.primaryText).toBe("Premieres Aug 14");
      expect(status.secondaryText).toBe("Season 1 · 12 episodes");
    });

    it("handles future season premiere for existing show", () => {
      const show: MediaItem = {
        id: 13,
        media_type: "tv",
        title: "Severance",
        number_of_seasons: 4,
        number_of_episodes: 34,
        next_season: {
          name: "Season 4",
          season_number: 4,
          air_date: "2026-09-18",
        },
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("upcoming");
      expect(status.primaryText).toBe("Season 4 premieres Sep 18");
      expect(status.secondaryText).toBe("3 seasons · 34 episodes released");
    });

    it("handles confirmed future season with date TBD", () => {
      const show: MediaItem = {
        id: 14,
        media_type: "tv",
        title: "Ted Lasso",
        status: "Returning Series",
        number_of_seasons: 3,
        number_of_episodes: 34,
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("confirmed_tbd");
      expect(status.primaryText).toBe("Season 4 confirmed");
      expect(status.secondaryText).toBe("Premiere date TBD");
    });

    it("uses honest fallback wording when total episode count is unknown", () => {
      const show: MediaItem = {
        id: 15,
        media_type: "tv",
        title: "Incomplete Data Show",
        last_episode_to_air: {
          season_number: 1,
          episode_number: 4,
        },
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("partially_available");
      expect(status.primaryText).toBe("4 episodes available"); // Does NOT fabricate "4 of 12"!
    });

    it("handles ended or canceled shows neutrally", () => {
      const show: MediaItem = {
        id: 16,
        media_type: "tv",
        title: "Canceled Show",
        status: "Canceled",
        number_of_episodes: 18,
        number_of_seasons: 2,
      };

      const status = buildQueueAvailabilityStatus(show, refDate);
      expect(status.state).toBe("complete");
      expect(status.primaryText).toBe("All 18 episodes available");
      expect(status.secondaryText).toBe("2 seasons");
    });

    it("handles TV series with a released new season (same color/available as other releases)", () => {
      const show: MediaItem = {
        id: 113962,
        media_type: "tv",
        title: "Lioness",
        release_date: "2023-07-23",
        next_season: {
          name: "Season 3",
          season_number: 3,
          air_date: "2026-08-02",
        },
      };

      // refDate is 2026-08-01, but test with refDate 2026-09-15 where 2026-08-02 is in the past
      const todayRef = new Date("2026-09-15T12:00:00Z");
      const status = buildQueueAvailabilityStatus(show, todayRef);
      expect(status.state).toBe("available");
      expect(status.primaryText).toBe("Released");
      expect(status.secondaryText).toBe("Released Aug 2, 2026");
      expect(status.date).toBe("2026-08-02");
    });

    it("handles TV series with an upcoming new season (same color/upcoming as other releases)", () => {
      const show: MediaItem = {
        id: 84773,
        media_type: "tv",
        title: "The Lord of the Rings: The Rings of Power",
        release_date: "2022-09-01",
        number_of_seasons: 3,
        next_season: {
          name: "Season 3",
          season_number: 3,
          air_date: "2026-11-10",
        },
      };

      const todayRef = new Date("2026-09-15T12:00:00Z");
      const status = buildQueueAvailabilityStatus(show, todayRef);
      expect(status.state).toBe("upcoming");
      expect(status.primaryText).toBe("Season 3 premieres Nov 10");
      expect(status.date).toBe("2026-11-10");
    });

    it("handles TV series with past premiere date and no future seasons (same color as released movies)", () => {
      const show: MediaItem = {
        id: 224941,
        media_type: "tv",
        title: "The Boroughs",
        release_date: "2026-05-21",
      };

      const todayRef = new Date("2026-09-15T12:00:00Z");
      const status = buildQueueAvailabilityStatus(show, todayRef);
      expect(status.state).toBe("available");
      expect(status.primaryText).toBe("Released");
      expect(status.secondaryText).toBe("Released May 21, 2026");
      expect(status.date).toBe("2026-05-21");
    });

    it("sorts queue items chronologically by effective release date for both available and upcoming titles", () => {
      const items: MediaItem[] = [
        {
          id: 1,
          media_type: "movie",
          title: "Eternal Sunshine of the Spotless Mind",
          release_date: "2004-03-19",
        },
        {
          id: 2,
          media_type: "tv",
          title: "Watership Down",
          release_date: "2018-12-22",
        },
        {
          id: 3,
          media_type: "movie",
          title: "Spider-Man: Brand New Day",
          release_date: "2026-07-31",
        },
        {
          id: 4,
          media_type: "tv",
          title: "Lioness",
          release_date: "2023-07-23",
          next_season: {
            name: "Season 3",
            season_number: 3,
            air_date: "2026-08-02",
          },
        },
        {
          id: 5,
          media_type: "movie",
          title: "The Social Reckoning",
          release_date: "2026-10-07",
        },
        {
          id: 6,
          media_type: "tv",
          title: "Cupertino",
          release_date: "2026-10-08",
        },
        {
          id: 7,
          media_type: "tv",
          title: "The Lord of the Rings: The Rings of Power",
          release_date: "2022-09-01",
          next_season: {
            name: "Season 3",
            season_number: 3,
            air_date: "2026-11-10",
          },
        },
        {
          id: 8,
          media_type: "movie",
          title: "Narnia: The Magician's Nephew",
          release_date: "2027-02-11",
        },
      ];

      const sorted = sortQueueItems(items);
      const titles = sorted.map((i) => i.title);

      // Available titles sort chronologically by release date:
      // 2004-03-19 < 2018-12-22 < 2026-07-31 < 2026-08-02 (Lioness Season 3)
      expect(titles.slice(0, 4)).toEqual([
        "Eternal Sunshine of the Spotless Mind",
        "Watership Down",
        "Spider-Man: Brand New Day",
        "Lioness",
      ]);

      // Upcoming titles sort chronologically by upcoming date:
      // 2026-10-07 < 2026-10-08 < 2026-11-10 (Rings of Power Season 3) < 2027-02-11
      expect(titles.slice(4)).toEqual([
        "The Social Reckoning",
        "Cupertino",
        "The Lord of the Rings: The Rings of Power",
        "Narnia: The Magician's Nephew",
      ]);
    });
  });
});
