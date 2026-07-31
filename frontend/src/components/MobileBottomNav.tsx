import React from "react";
import type { TabType } from "./Tabs";

interface MobileBottomNavProps {
  activeTab: TabType;
  onChangeTab: (tab: TabType) => void;
}

const NAV_ITEMS: { id: TabType; label: string; icon: string }[] = [
  { id: "watchlist", label: "Queue", icon: "🍿" },
  { id: "following", label: "Monitoring", icon: "🔔" },
  { id: "library", label: "Library", icon: "📚" },
  { id: "rated", label: "Ratings", icon: "⭐" },
  { id: "search", label: "Search", icon: "🔎" },
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
          const isActive = activeTab === item.id;
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
              <span className="mobile-nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="mobile-nav-label">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
