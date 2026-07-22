

export type TabType = "watchlist" | "upcoming" | "theatres" | "trending" | "on-air" | "search" | "library" | "following" | "rated";


interface TabsProps {
  tabsList: { id: TabType; label: string }[];
  activeTab: TabType;
  onChangeTab: (tab: TabType) => void;
}

export function Tabs({ tabsList, activeTab, onChangeTab }: TabsProps) {
  return (
    <nav className="tabs">
      {tabsList.map((entry) => (
        <button
          key={entry.id}
          className={`tab ${activeTab === entry.id ? "active" : ""}`}
          onClick={() => onChangeTab(entry.id)}
        >
          {entry.label}
        </button>
      ))}
      {activeTab === "search" ? <span className="tab active">Search</span> : null}
    </nav>
  );
}
