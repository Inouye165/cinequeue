import React, { useState } from "react";

interface SearchHeaderProps {
  query: string;
  setQuery: (q: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  user?: { email?: string | null; display_name?: string | null; photo_url?: string | null } | null;
  onLogout?: () => void;
  onOpenAgentModal?: (tab: "chat" | "settings" | "logs") => void;
}

export function SearchHeader({ query, setQuery, onSubmit, user, onLogout, onOpenAgentModal }: SearchHeaderProps) {
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);

  return (
    <header className="hero">
      <div className="hero-top-row">
        <div className="hero-brand">
          <div className="brand-title-wrap">
            <span className="brand-logo-icon" aria-hidden="true">🍿</span>
            <h1>Cinequeue</h1>
          </div>
          <p className="hero-description">
            Track movies & TV, release countdowns, streaming availability, prices, and headlines in one place.
          </p>
        </div>

        {user && (
          <div className="user-info-dropdown-container">
            <button
              className="avatar-dropdown-trigger"
              onClick={() => setShowAvatarMenu((prev) => !prev)}
              aria-label="User Account and AI Agent Menu"
            >
              {user.photo_url ? (
                <img src={user.photo_url} alt={user.display_name || user.email || "User"} className="user-avatar" />
              ) : (
                <div className="user-avatar-fallback">
                  {((user.display_name || user.email || "U")[0]).toUpperCase()}
                </div>
              )}
              <span className="user-name-compact">{user.display_name?.split(" ")[0] || user.email?.split("@")[0]}</span>
              <span className="dropdown-caret">▼</span>
            </button>

            {showAvatarMenu && (
              <>
                <div
                  className="dropdown-backdrop"
                  onClick={() => setShowAvatarMenu(false)}
                />
                <div className="avatar-dropdown-menu">
                  <div className="dropdown-user-header">
                    <span className="dropdown-user-name">{user.display_name || "User Account"}</span>
                    <span className="dropdown-user-email">{user.email}</span>
                  </div>
                  <hr className="dropdown-divider" />
                  {onOpenAgentModal && (
                    <>
                      <button
                        className="dropdown-menu-item"
                        onClick={() => {
                          setShowAvatarMenu(false);
                          onOpenAgentModal("chat");
                        }}
                      >
                        <span className="menu-item-icon">💬</span> Chat with AI Agent
                      </button>
                      <button
                        className="dropdown-menu-item"
                        onClick={() => {
                          setShowAvatarMenu(false);
                          onOpenAgentModal("settings");
                        }}
                      >
                        <span className="menu-item-icon">⚙️</span> AI Personality & Settings
                      </button>
                      <button
                        className="dropdown-menu-item"
                        onClick={() => {
                          setShowAvatarMenu(false);
                          onOpenAgentModal("logs");
                        }}
                      >
                        <span className="menu-item-icon">📊</span> AI Debugging & Logs
                      </button>
                      <hr className="dropdown-divider" />
                    </>
                  )}
                  {onLogout && (
                    <button
                      className="dropdown-menu-item logout-item"
                      onClick={() => {
                        setShowAvatarMenu(false);
                        onLogout();
                      }}
                    >
                      <span className="menu-item-icon">🚪</span> Sign Out
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <form className="search-bar" onSubmit={onSubmit} role="search">
        <div className="search-input-wrap">
          <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search movies & TV shows…"
            aria-label="Search movies and TV shows"
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
          />
          {query.trim() && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setQuery("")}
              aria-label="Clear search query"
            >
              ✕
            </button>
          )}
        </div>
        <button type="submit" className="search-submit-btn" aria-label="Submit search">
          Search
        </button>
      </form>
    </header>
  );
}
