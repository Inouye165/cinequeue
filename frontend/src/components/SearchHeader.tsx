import React, { useState } from "react";
import { AccountSheet } from "./AccountSheet";

interface SearchHeaderProps {
  query: string;
  setQuery: (q: string) => void;
  onSubmit: (e: React.FormEvent) => void;
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
  user,
  onLogout,
  onOpenAgentModal,
  ownerId = "local_owner",
  onDataCleared,
}: SearchHeaderProps) {
  const [showAccountSheet, setShowAccountSheet] = useState(false);

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

      {/* Row 2: Streamlined Integrated Search Field */}
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
        </div>
      </form>

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
