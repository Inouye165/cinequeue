import React, { useState } from "react";
import { AccountSheet } from "./AccountSheet";
import { SearchFiltersPanel } from "./SearchFiltersPanel";
import type { SearchFilterState } from "../types";

interface SearchHeaderProps {
  query: string;
  setQuery: (q: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  filters?: SearchFilterState;
  onUpdateFilters?: (newFilters: SearchFilterState) => void;
  onResetFilters?: () => void;
  user?: { email?: string | null; display_name?: string | null; photo_url?: string | null } | null;
  onLogout?: () => void;
  onOpenAgentModal?: (tab: "chat" | "settings" | "logs") => void;
  ownerId?: string;
  onDataCleared?: () => void;
}

export function SearchHeader({
  query,
  setQuery,
  onSubmit,
  filters,
  onUpdateFilters,
  onResetFilters,
  user,
  onLogout,
  onOpenAgentModal,
  ownerId = "local_owner",
  onDataCleared,
}: SearchHeaderProps) {
  const [showAccountSheet, setShowAccountSheet] = useState(false);
  const [showFiltersPanel, setShowFiltersPanel] = useState(false);

  const activeFiltersCount = filters
    ? (filters.actors.length > 0 ? filters.actors.length : 0) +
      (filters.director.trim() ? 1 : 0) +
      (filters.yearType !== "any" ? 1 : 0) +
      (filters.mediaType !== "all" ? 1 : 0)
    : 0;

  const handleRemoveActor = (actorToRemove: string) => {
    if (!filters || !onUpdateFilters) return;
    onUpdateFilters({
      ...filters,
      actors: filters.actors.filter((a) => a !== actorToRemove),
    });
  };

  const handleClearDirector = () => {
    if (!filters || !onUpdateFilters) return;
    onUpdateFilters({
      ...filters,
      director: "",
    });
  };

  const handleClearYear = () => {
    if (!filters || !onUpdateFilters) return;
    onUpdateFilters({
      ...filters,
      yearType: "any",
      year: undefined,
      yearBefore: undefined,
      yearAfter: undefined,
      yearFrom: undefined,
      yearTo: undefined,
    });
  };

  const handleClearMediaType = () => {
    if (!filters || !onUpdateFilters) return;
    onUpdateFilters({
      ...filters,
      mediaType: "all",
    });
  };

  return (
    <header className="mobile-app-bar" role="banner">
      {/* Row 1: Brand Wordmark + Compact User Avatar */}
      <div className="app-bar-top-row">
        <div className="brand-wordmark">
          <span className="brand-icon" aria-hidden="true">🍿</span>
          <h1 className="brand-name">CineQueue</h1>
        </div>

        {user && (
          <button
            type="button"
            className="avatar-icon-btn"
            onClick={() => setShowAccountSheet(true)}
            aria-label={`Open Account menu for ${user.display_name || user.email || "User"}`}
          >
            {user.photo_url ? (
              <img
                src={user.photo_url}
                alt={user.display_name || user.email || "User avatar"}
                className="avatar-img"
              />
            ) : (
              <span className="avatar-fallback">
                {((user.display_name || user.email || "U")[0]).toUpperCase()}
              </span>
            )}
          </button>
        )}
      </div>

      {/* Row 2: Streamlined Integrated Search Field + Filters Button */}
      <form className="mobile-search-form" onSubmit={onSubmit} role="search">
        <div className="integrated-search-box">
          <button type="submit" className="search-icon-btn" aria-label="Submit search">
            <svg
              className="search-svg-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          <input
            type="search"
            className="integrated-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search movies & TV shows..."
            aria-label="Search movies and TV"
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
          />
          {query.trim() ? (
            <button
              type="button"
              className="search-clear-icon-btn"
              onClick={() => setQuery("")}
              aria-label="Clear search"
            >
              ✕
            </button>
          ) : null}

          {/* Filter toggle button */}
          <button
            type="button"
            className={`search-filter-toggle-btn ${activeFiltersCount > 0 ? "active" : ""}`}
            onClick={() => setShowFiltersPanel(!showFiltersPanel)}
            aria-label={`Search filters, ${activeFiltersCount} active`}
            title="Advanced Search Filters"
          >
            <svg
              className="filter-toggle-svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
            </svg>
            {activeFiltersCount > 0 && (
              <span className="filter-count-badge" aria-hidden="true">
                {activeFiltersCount}
              </span>
            )}
          </button>
        </div>
      </form>

      {/* Active Filter Pills Bar (Quick removal) */}
      {filters && activeFiltersCount > 0 && (
        <div className="active-filters-bar" aria-label="Active search filters">
          {filters.actors.map((actor) => (
            <span key={actor} className="active-filter-pill">
              <span>🎭 {actor}</span>
              <button
                type="button"
                onClick={() => handleRemoveActor(actor)}
                aria-label={`Remove actor filter ${actor}`}
              >
                ✕
              </button>
            </span>
          ))}

          {filters.director.trim() && (
            <span className="active-filter-pill">
              <span>🎬 {filters.director}</span>
              <button
                type="button"
                onClick={handleClearDirector}
                aria-label="Remove director filter"
              >
                ✕
              </button>
            </span>
          )}

          {filters.yearType === "exact" && filters.year && (
            <span className="active-filter-pill">
              <span>📅 {filters.year}</span>
              <button
                type="button"
                onClick={handleClearYear}
                aria-label="Remove year filter"
              >
                ✕
              </button>
            </span>
          )}

          {filters.yearType === "before" && filters.yearBefore && (
            <span className="active-filter-pill">
              <span>📅 Before {filters.yearBefore}</span>
              <button
                type="button"
                onClick={handleClearYear}
                aria-label="Remove before year filter"
              >
                ✕
              </button>
            </span>
          )}

          {filters.yearType === "after" && filters.yearAfter && (
            <span className="active-filter-pill">
              <span>📅 After {filters.yearAfter}</span>
              <button
                type="button"
                onClick={handleClearYear}
                aria-label="Remove after year filter"
              >
                ✕
              </button>
            </span>
          )}

          {filters.yearType === "range" && (filters.yearFrom || filters.yearTo) && (
            <span className="active-filter-pill">
              <span>📅 {filters.yearFrom || "..."}–{filters.yearTo || "..."}</span>
              <button
                type="button"
                onClick={handleClearYear}
                aria-label="Remove year range filter"
              >
                ✕
              </button>
            </span>
          )}

          {filters.mediaType !== "all" && (
            <span className="active-filter-pill">
              <span>{filters.mediaType === "movie" ? "🎬 Movies" : "📺 TV Shows"}</span>
              <button
                type="button"
                onClick={handleClearMediaType}
                aria-label="Remove media type filter"
              >
                ✕
              </button>
            </span>
          )}

          {onResetFilters && (
            <button
              type="button"
              className="active-filters-clear-all"
              onClick={onResetFilters}
            >
              Clear all
            </button>
          )}
        </div>
      )}

      {/* Advanced Filters Panel / Drawer */}
      {filters && onUpdateFilters && (
        <SearchFiltersPanel
          isOpen={showFiltersPanel}
          onClose={() => setShowFiltersPanel(false)}
          filters={filters}
          onUpdateFilters={onUpdateFilters}
          onApplyAndSearch={() => {
            const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
            onSubmit(fakeEvent);
          }}
          onResetFilters={() => {
            if (onResetFilters) onResetFilters();
          }}
        />
      )}

      {/* Account & Sync Modal Sheet */}
      <AccountSheet
        isOpen={showAccountSheet}
        onClose={() => setShowAccountSheet(false)}
        user={user}
        onLogout={onLogout}
        onOpenAgentModal={onOpenAgentModal}
        ownerId={ownerId}
        onDataCleared={onDataCleared}
      />
    </header>
  );
}
