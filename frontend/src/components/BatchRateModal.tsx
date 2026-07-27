import React, { useState, useEffect, useRef } from "react";
import { api } from "../api";
import { StarRating } from "./StarRating";
import type { MediaItem } from "../types";

interface DraftRatingItem {
  media_type: string;
  tmdb_id: number;
  title: string;
  poster_path: string | null;
  release_date: string | null;
  poster_url?: string;
  rating: number;
}

interface BatchRateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRatingsAdded: () => void;
}

export const BatchRateModal: React.FC<BatchRateModalProps> = ({
  isOpen,
  onClose,
  onRatingsAdded,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MediaItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [draftItems, setDraftItems] = useState<DraftRatingItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Debounced search logic
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (!searchQuery.trim()) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const results = await api.search(searchQuery.trim());
        setSearchResults(results || []);
      } catch (err) {
        console.error("Failed to search movies for rating batch:", err);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchQuery]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setSearchQuery("");
      setSearchResults([]);
      setDraftItems([]);
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelectItem = (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as any).tmdb_id : item.id;
    const mediaType = item.media_type || "movie";
    const posterPath = "poster_path" in item ? (item as any).poster_path || null : null;

    // Prevent duplicate entries in draft list
    const exists = draftItems.some(
      (d) => d.media_type === mediaType && d.tmdb_id === tmdbId
    );

    if (exists) {
      setError(`"${item.title}" is already in your batch list.`);
      return;
    }

    setError(null);
    setDraftItems((prev) => [
      ...prev,
      {
        media_type: mediaType,
        tmdb_id: tmdbId,
        title: item.title,
        poster_path: posterPath,
        release_date: item.release_date || null,
        poster_url: item.poster_url || undefined,
        rating: 5, // Default rating 5 stars
      },
    ]);

    setSearchQuery("");
    setSearchResults([]);
  };

  const handleRatingChange = (index: number, newRating: number) => {
    setDraftItems((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], rating: newRating };
      return updated;
    });
  };

  const handleRemoveDraftItem = (index: number) => {
    setDraftItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmitBatch = async () => {
    if (draftItems.length === 0) {
      setError("Please add at least one movie to rate.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await api.rateMoviesBatch(
        draftItems.map((item) => ({
          media_type: item.media_type,
          tmdb_id: item.tmdb_id,
          title: item.title,
          poster_path: item.poster_path,
          release_date: item.release_date,
          rating: item.rating,
        }))
      );

      onRatingsAdded();
      onClose();
    } catch (err) {
      console.error("Batch rate failed:", err);
      setError(err instanceof Error ? err.message : "Failed to save ratings");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-content batch-rate-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mobile-sheet-handle" aria-hidden="true" />
        <div className="modal-header">
          <h2 style={{ margin: 0, fontSize: "1.3rem" }}>⭐ Batch Add Movie Ratings</h2>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "16px 0" }}>
          {error && <div className="error-banner">{error}</div>}

          {/* Search Box */}
          <div className="batch-search-container" style={{ position: "relative" }}>
            <label style={{ display: "block", marginBottom: "6px", fontSize: "0.9rem", fontWeight: 600 }}>
              Search & Add Movies or Shows:
            </label>
            <input
              type="text"
              className="search-input"
              placeholder="Type a title (e.g., Inception, Dune)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: "100%", padding: "10px 14px", borderRadius: "8px" }}
              autoFocus
            />

            {/* Search Dropdown Results */}
            {(searchResults.length > 0 || isSearching) && (
              <div
                className="search-dropdown-menu"
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  right: 0,
                  background: "var(--color-bg-card, #1a1e2e)",
                  border: "1px solid var(--color-border, #2e3650)",
                  borderRadius: "8px",
                  maxHeight: "220px",
                  overflowY: "auto",
                  zIndex: 100,
                  marginTop: "4px",
                  boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
                }}
              >
                {isSearching ? (
                  <div style={{ padding: "12px", textAlign: "center", color: "#8a94a6" }}>Searching...</div>
                ) : (
                  searchResults.map((item) => {
                    const posterPath = "poster_path" in item ? (item as any).poster_path : null;
                    return (
                      <div
                        key={`${item.media_type}:${item.id}`}
                        className="search-result-row"
                        onClick={() => handleSelectItem(item)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "12px",
                          padding: "8px 12px",
                          cursor: "pointer",
                          borderBottom: "1px solid rgba(255,255,255,0.05)",
                        }}
                      >
                        {posterPath ? (
                          <img
                            src={`https://image.tmdb.org/t/p/w92${posterPath}`}
                            alt={item.title}
                            style={{ width: "32px", height: "48px", objectFit: "cover", borderRadius: "4px" }}
                          />
                        ) : (
                          <div style={{ width: "32px", height: "48px", background: "#2e3650", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.7rem" }}>
                            🎬
                          </div>
                        )}
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{item.title}</div>
                          <div style={{ fontSize: "0.8rem", color: "#8a94a6" }}>
                            {item.release_date ? item.release_date.slice(0, 4) : "N/A"} • {item.media_type === "tv" ? "TV Show" : "Movie"}
                          </div>
                        </div>
                        <span className="btn-secondary" style={{ padding: "4px 10px", fontSize: "0.8rem" }}>+ Add</span>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>

          {/* Draft List */}
          <div className="draft-ratings-section">
            <h3 style={{ fontSize: "1rem", marginBottom: "10px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Movies to Rate ({draftItems.length})</span>
              {draftItems.length > 0 && (
                <button
                  type="button"
                  className="text-btn"
                  onClick={() => setDraftItems([])}
                  style={{ fontSize: "0.8rem", color: "#ef4444", background: "none", border: "none", cursor: "pointer" }}
                >
                  Clear All
                </button>
              )}
            </h3>

            {draftItems.length === 0 ? (
              <div style={{ textAlign: "center", padding: "24px", background: "rgba(255,255,255,0.02)", borderRadius: "8px", border: "1px dashed var(--color-border, #2e3650)", color: "#8a94a6" }}>
                Use the search box above to add movies you want to rate.
              </div>
            ) : (
              <div className="draft-items-list" style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "280px", overflowY: "auto" }}>
                {draftItems.map((item, idx) => (
                  <div
                    key={`${item.media_type}:${item.tmdb_id}`}
                    className="draft-item-card"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "12px",
                      background: "var(--color-bg-card, #1a1e2e)",
                      padding: "10px 14px",
                      borderRadius: "8px",
                      border: "1px solid var(--color-border, #2e3650)",
                    }}
                  >
                    {item.poster_url || item.poster_path ? (
                      <img
                        src={item.poster_url || `https://image.tmdb.org/t/p/w92${item.poster_path}`}
                        alt={item.title}
                        style={{ width: "36px", height: "54px", objectFit: "cover", borderRadius: "4px" }}
                      />
                    ) : (
                      <div style={{ width: "36px", height: "54px", background: "#2e3650", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.75rem" }}>
                        🎬
                      </div>
                    )}

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {item.title}
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "#8a94a6" }}>
                        {item.release_date ? item.release_date.slice(0, 4) : "N/A"}
                      </div>
                    </div>

                    {/* Interactive Star Rating */}
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <StarRating
                        rating={item.rating}
                        onRate={(r) => handleRatingChange(idx, r)}
                        size="md"
                      />
                      <button
                        type="button"
                        onClick={() => handleRemoveDraftItem(idx)}
                        style={{
                          background: "rgba(239, 68, 68, 0.15)",
                          color: "#ef4444",
                          border: "none",
                          borderRadius: "6px",
                          width: "32px",
                          height: "32px",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: "1rem",
                        }}
                        title="Remove from batch"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Modal Actions */}
        <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: "12px", paddingTop: "12px", borderTop: "1px solid var(--color-border, #2e3650)" }}>
          <button className="btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={() => void handleSubmitBatch()}
            disabled={submitting || draftItems.length === 0}
            style={{ display: "flex", alignItems: "center", gap: "8px" }}
          >
            {submitting ? "Saving Ratings..." : `Save ${draftItems.length} Rating${draftItems.length !== 1 ? "s" : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
};
