import React from "react";
import type { TabType } from "./Tabs";

interface MobileBottomNavProps {
  activeTab: TabType;
  onChangeTab: (tab: TabType) => void;
}

const DISCOVERY_TABS: TabType[] = ["trending", "upcoming", "theatres", "on-air"];

interface NavItemConfig {
  id: TabType;
  label: string;
  matchTabs?: TabType[];
  renderIcon: (active: boolean) => React.ReactNode;
}

const NAV_ITEMS: NavItemConfig[] = [
  {
    id: "watchlist",
    label: "Queue",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    id: "sports",
    label: "Sports",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
        <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
        <path d="M4 22h16" />
        <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
        <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
        <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
      </svg>
    ),
  },
  {
    id: "following",
    label: "Monitoring",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    ),
  },
  {
    id: "library",
    label: "Library",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
  },
  {
    id: "rated",
    label: "Ratings",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
  },
  {
    id: "trending",
    label: "Discover",
    matchTabs: DISCOVERY_TABS,
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth={active ? "2.2" : "1.8"} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill={active ? "currentColor" : "none"} />
      </svg>
    ),
  },
  {
    id: "search",
    label: "Search",
    renderIcon: (active) => (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth={active ? "2.5" : "1.9"} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
];

export function MobileBottomNav({ activeTab, onChangeTab }: MobileBottomNavProps) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      const nextIndex = (index + 1) % NAV_ITEMS.length;
      onChangeTab(NAV_ITEMS[nextIndex].id);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      const prevIndex = (index - 1 + NAV_ITEMS.length) % NAV_ITEMS.length;
      onChangeTab(NAV_ITEMS[prevIndex].id);
    }
  };

  return (
    <nav className="mobile-bottom-nav" aria-label="Mobile Navigation" role="navigation">
      <div className="mobile-bottom-nav-inner" role="tablist">
        {NAV_ITEMS.map((item, idx) => {
          const isActive = item.matchTabs ? item.matchTabs.includes(activeTab) : activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`mob-nav-${item.id}`}
              aria-controls={`tabpanel-${item.id}`}
              aria-selected={isActive}
              aria-current={isActive ? "page" : undefined}
              tabIndex={isActive ? 0 : -1}
              className={`mobile-nav-item ${isActive ? "active" : ""}`}
              onClick={() => onChangeTab(item.id)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
            >
              <span className="mobile-nav-icon-pill" aria-hidden="true">
                {item.renderIcon(isActive)}
              </span>
              <span className="mobile-nav-label">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
