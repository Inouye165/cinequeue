import React, { useState } from "react";
import type { SearchFilterState, YearFilterType } from "../types";

interface SearchFiltersPanelProps {
  isOpen: boolean;
  onClose: () => void;
  filters: SearchFilterState;
  onUpdateFilters: (newFilters: SearchFilterState) => void;
  onApplyAndSearch: () => void;
  onResetFilters: () => void;
}

export function SearchFiltersPanel({
  isOpen,
  onClose,
  filters,
  onUpdateFilters,
  onApplyAndSearch,
  onResetFilters,
}: SearchFiltersPanelProps) {
  const [actorInput, setActorInput] = useState("");

  if (!isOpen) return null;

  const handleAddActor = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = actorInput.trim();
    if (!trimmed) return;
    if (!filters.actors.includes(trimmed)) {
      onUpdateFilters({
        ...filters,
        actors: [...filters.actors, trimmed],
      });
    }
    setActorInput("");
  };

  const handleRemoveActor = (actorToRemove: string) => {
    onUpdateFilters({
      ...filters,
      actors: filters.actors.filter((a) => a !== actorToRemove),
    });
  };

  const handleYearTypeChange = (type: YearFilterType) => {
    onUpdateFilters({
      ...filters,
      yearType: type,
    });
  };

  const activeCount =
    (filters.actors.length > 0 ? filters.actors.length : 0) +
    (filters.director.trim() ? 1 : 0) +
    (filters.yearType !== "any" ? 1 : 0) +
    (filters.mediaType !== "all" ? 1 : 0);

  return (
    <div className="search-filters-drawer" role="region" aria-label="Search Filters">
      <div className="filters-header">
        <div className="filters-header-title">
          <svg className="filters-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          <h3>Advanced Search Filters</h3>
          {activeCount > 0 && <span className="filters-active-badge">{activeCount} active</span>}
        </div>
        <button
          type="button"
          className="filters-close-btn"
          onClick={onClose}
          aria-label="Close search filters"
        >
          ✕
        </button>
      </div>

      <div className="filters-body">
        {/* Actors filter */}
        <div className="filter-group">
          <label className="filter-label" htmlFor="actor-input-field">
            <span>🎭 Actors</span>
            <span className="filter-label-hint">Search for one or multiple actors</span>
          </label>
          <div className="actor-input-row">
            <input
              id="actor-input-field"
              type="text"
              className="filter-text-input"
              value={actorInput}
              onChange={(e) => setActorInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddActor();
                }
              }}
              placeholder="e.g. Tom Hanks, Brad Pitt..."
              aria-label="Actor name"
            />
            <button
              type="button"
              className="filter-add-btn"
              onClick={() => handleAddActor()}
              disabled={!actorInput.trim()}
              aria-label="Add actor"
            >
              + Add
            </button>
          </div>

          {filters.actors.length > 0 && (
            <div className="filter-chips-container" aria-label="Selected actors list">
              {filters.actors.map((actor) => (
                <span key={actor} className="filter-chip">
                  <span>{actor}</span>
                  <button
                    type="button"
                    className="filter-chip-remove"
                    onClick={() => handleRemoveActor(actor)}
                    aria-label={`Remove actor ${actor}`}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Director filter */}
        <div className="filter-group">
          <label className="filter-label" htmlFor="director-input-field">
            <span>🎬 Director</span>
            <span className="filter-label-hint">Find movies directed by</span>
          </label>
          <div className="filter-input-with-clear">
            <input
              id="director-input-field"
              type="text"
              className="filter-text-input"
              value={filters.director}
              onChange={(e) =>
                onUpdateFilters({
                  ...filters,
                  director: e.target.value,
                })
              }
              placeholder="e.g. Christopher Nolan, Greta Gerwig..."
              aria-label="Director name"
            />
            {filters.director ? (
              <button
                type="button"
                className="filter-input-clear-btn"
                onClick={() => onUpdateFilters({ ...filters, director: "" })}
                aria-label="Clear director"
              >
                ✕
              </button>
            ) : null}
          </div>
        </div>

        {/* Year / Date Range filter */}
        <div className="filter-group">
          <label className="filter-label">
            <span>📅 Release Year / Date Range</span>
          </label>
          <div className="segmented-filter-pills" role="radiogroup" aria-label="Year filter type">
            {(
              [
                { id: "any", label: "Any Time" },
                { id: "exact", label: "Exact Year" },
                { id: "before", label: "Before Year" },
                { id: "after", label: "After Year" },
                { id: "range", label: "Year Range" },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={`segmented-pill ${filters.yearType === opt.id ? "active" : ""}`}
                onClick={() => handleYearTypeChange(opt.id)}
                role="radio"
                aria-checked={filters.yearType === opt.id}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Dynamic year inputs based on selected yearType */}
          <div className="year-inputs-container">
            {filters.yearType === "exact" && (
              <div className="single-year-input-row">
                <label htmlFor="exact-year-input" className="sub-label">Release Year:</label>
                <input
                  id="exact-year-input"
                  type="number"
                  className="filter-number-input"
                  min="1900"
                  max="2099"
                  placeholder="e.g. 1999"
                  value={filters.year || ""}
                  onChange={(e) =>
                    onUpdateFilters({
                      ...filters,
                      year: e.target.value ? parseInt(e.target.value, 10) : undefined,
                    })
                  }
                  aria-label="Exact release year"
                />
              </div>
            )}

            {filters.yearType === "before" && (
              <div className="single-year-input-row">
                <label htmlFor="before-year-input" className="sub-label">Released before / in:</label>
                <input
                  id="before-year-input"
                  type="number"
                  className="filter-number-input"
                  min="1900"
                  max="2099"
                  placeholder="e.g. 2000"
                  value={filters.yearBefore || ""}
                  onChange={(e) =>
                    onUpdateFilters({
                      ...filters,
                      yearBefore: e.target.value ? parseInt(e.target.value, 10) : undefined,
                    })
                  }
                  aria-label="Released before year"
                />
              </div>
            )}

            {filters.yearType === "after" && (
              <div className="single-year-input-row">
                <label htmlFor="after-year-input" className="sub-label">Released after / in:</label>
                <input
                  id="after-year-input"
                  type="number"
                  className="filter-number-input"
                  min="1900"
                  max="2099"
                  placeholder="e.g. 2015"
                  value={filters.yearAfter || ""}
                  onChange={(e) =>
                    onUpdateFilters({
                      ...filters,
                      yearAfter: e.target.value ? parseInt(e.target.value, 10) : undefined,
                    })
                  }
                  aria-label="Released after year"
                />
              </div>
            )}

            {filters.yearType === "range" && (
              <div className="range-year-inputs-row">
                <div className="range-input-item">
                  <label htmlFor="range-from-input" className="sub-label">From Year:</label>
                  <input
                    id="range-from-input"
                    type="number"
                    className="filter-number-input"
                    min="1900"
                    max="2099"
                    placeholder="e.g. 1990"
                    value={filters.yearFrom || ""}
                    onChange={(e) =>
                      onUpdateFilters({
                        ...filters,
                        yearFrom: e.target.value ? parseInt(e.target.value, 10) : undefined,
                      })
                    }
                    aria-label="From year"
                  />
                </div>
                <span className="range-separator">—</span>
                <div className="range-input-item">
                  <label htmlFor="range-to-input" className="sub-label">To Year:</label>
                  <input
                    id="range-to-input"
                    type="number"
                    className="filter-number-input"
                    min="1900"
                    max="2099"
                    placeholder="e.g. 2005"
                    value={filters.yearTo || ""}
                    onChange={(e) =>
                      onUpdateFilters({
                        ...filters,
                        yearTo: e.target.value ? parseInt(e.target.value, 10) : undefined,
                      })
                    }
                    aria-label="To year"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Media Type filter */}
        <div className="filter-group">
          <label className="filter-label">
            <span>📺 Media Type</span>
          </label>
          <div className="segmented-filter-pills" role="radiogroup" aria-label="Media type filter">
            {(
              [
                { id: "all", label: "All Media" },
                { id: "movie", label: "🎬 Movies" },
                { id: "tv", label: "📺 TV Shows" },
              ] as const
            ).map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={`segmented-pill ${filters.mediaType === opt.id ? "active" : ""}`}
                onClick={() =>
                  onUpdateFilters({
                    ...filters,
                    mediaType: opt.id,
                  })
                }
                role="radio"
                aria-checked={filters.mediaType === opt.id}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filter Action Buttons */}
      <div className="filters-footer">
        <button
          type="button"
          className="filters-reset-btn"
          onClick={onResetFilters}
          disabled={activeCount === 0}
        >
          Reset Filters
        </button>
        <button
          type="button"
          className="filters-apply-btn"
          onClick={() => {
            onApplyAndSearch();
            onClose();
          }}
        >
          Apply & Search
        </button>
      </div>
    </div>
  );
}
