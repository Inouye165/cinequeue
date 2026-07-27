import { useEffect, useRef } from "react";

export type TabType =
  | "watchlist"
  | "upcoming"
  | "theatres"
  | "trending"
  | "on-air"
  | "search"
  | "library"
  | "following"
  | "rated";

interface TabsProps {
  tabsList: { id: TabType; label: string }[];
  activeTab: TabType;
  onChangeTab: (tab: TabType) => void;
}

export function Tabs({ tabsList, activeTab, onChangeTab }: TabsProps) {
  const activeTabRef = useRef<HTMLButtonElement | HTMLSpanElement | null>(null);

  useEffect(() => {
    if (activeTabRef.current) {
      const prefersReducedMotion =
        typeof window !== "undefined" &&
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      activeTabRef.current.scrollIntoView({
        behavior: prefersReducedMotion ? "auto" : "smooth",
        inline: "nearest",
        block: "nearest",
      });
    }
  }, [activeTab]);

  const handleTabClick = (id: TabType) => {
    onChangeTab(id);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      const nextIndex = (index + 1) % tabsList.length;
      onChangeTab(tabsList[nextIndex].id);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      const prevIndex = (index - 1 + tabsList.length) % tabsList.length;
      onChangeTab(tabsList[prevIndex].id);
    }
  };

  return (
    <div className="tabs-outer-wrap">
      <nav className="tabs" aria-label="Navigation Sections" role="tablist">
        {tabsList.map((entry, idx) => {
          const isActive = activeTab === entry.id;
          return (
            <button
              key={entry.id}
              ref={isActive ? (el) => { activeTabRef.current = el; } : null}
              role="tab"
              id={`tab-${entry.id}`}
              aria-controls={`tabpanel-${entry.id}`}
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              className={`tab ${isActive ? "active" : ""}`}
              onClick={() => handleTabClick(entry.id)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
            >
              {entry.label}
            </button>
          );
        })}
        {activeTab === "search" ? (
          <span
            ref={(el) => { activeTabRef.current = el; }}
            className="tab active"
            role="tab"
            id="tab-search"
            aria-selected={true}
            tabIndex={0}
          >
            Search Results
          </span>
        ) : null}
      </nav>
    </div>
  );
}
