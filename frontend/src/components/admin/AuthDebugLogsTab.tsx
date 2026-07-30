import { useState, useEffect, useCallback } from "react";
import {
  getAuthDebugLogs,
  clearAuthDebugLogs,
  subscribeAuthDebugLog,
  type AuthDebugEntry,
} from "../../utils/authDebugLog";

/**
 * Auth Debug Logs tab for the Admin Dashboard.
 * Shows a live-updating, searchable, filterable table of timestamped auth debug entries.
 */
export function AuthDebugLogsTab() {
  const [logs, setLogs] = useState<AuthDebugEntry[]>([]);
  const [search, setSearch] = useState("");
  const [levelFilter, setLevelFilter] = useState<string>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);

  // Subscribe to log updates
  useEffect(() => {
    const refresh = () => setLogs(getAuthDebugLogs());
    refresh();
    const unsub = subscribeAuthDebugLog(refresh);
    // Also poll every 2s as a fallback
    const interval = setInterval(refresh, 2000);
    return () => {
      unsub();
      clearInterval(interval);
    };
  }, []);

  // Auto-scroll the table to the bottom when new logs arrive
  const tableRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (node && autoScroll) {
        node.scrollTop = node.scrollHeight;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [logs, autoScroll],
  );

  const filtered = logs.filter((entry) => {
    if (levelFilter !== "all" && entry.level !== levelFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (
        !entry.label.toLowerCase().includes(q) &&
        !JSON.stringify(entry.detail || {}).toLowerCase().includes(q)
      ) {
        return false;
      }
    }
    return true;
  });

  const handleCopyAll = () => {
    const text = JSON.stringify(filtered, null, 2);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleClear = () => {
    clearAuthDebugLogs();
    setLogs([]);
  };

  const levelColor = (level: AuthDebugEntry["level"]) => {
    switch (level) {
      case "error":
        return "#ef4444";
      case "warn":
        return "#f59e0b";
      case "info":
        return "#60a5fa";
      case "debug":
        return "#9ca3af";
    }
  };

  const deltaColor = (deltaMs: number) => {
    if (deltaMs > 5000) return "#ef4444";
    if (deltaMs > 2000) return "#f59e0b";
    if (deltaMs > 500) return "#fbbf24";
    return "#6ee7b7";
  };

  return (
    <div className="admin-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>🔍 Auth Debug Logs ({logs.length} entries)</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.85rem", color: "var(--text-muted)" }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <button className="admin-btn admin-btn-primary" onClick={handleCopyAll} style={{ fontSize: "0.8rem", padding: "4px 10px" }}>
            {copied ? "✅ Copied!" : "📋 Copy JSON"}
          </button>
          <button className="admin-btn admin-btn-danger" onClick={handleClear} style={{ fontSize: "0.8rem", padding: "4px 10px" }}>
            🗑 Clear
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="text"
          className="admin-input"
          style={{ maxWidth: 300 }}
          placeholder="Search labels or details…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="admin-input"
          style={{ maxWidth: 140 }}
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
        >
          <option value="all">All Levels</option>
          <option value="error">Error</option>
          <option value="warn">Warn</option>
          <option value="info">Info</option>
          <option value="debug">Debug</option>
        </select>
        <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Showing {filtered.length} / {logs.length}
        </span>
      </div>

      {/* Table */}
      <div
        ref={tableRef}
        className="admin-table-container"
        style={{ maxHeight: 480, overflowY: "auto" }}
      >
        {filtered.length === 0 ? (
          <p style={{ color: "var(--text-muted)", padding: 16 }}>
            No debug log entries yet. Try logging in to generate entries.
          </p>
        ) : (
          <table className="admin-table" style={{ fontSize: "0.8rem" }}>
            <thead>
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th style={{ width: 80 }}>Level</th>
                <th style={{ width: 100 }}>Elapsed</th>
                <th style={{ width: 80 }}>Δ ms</th>
                <th style={{ width: 190 }}>Timestamp</th>
                <th>Label</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr
                  key={entry.seq}
                  style={{
                    background:
                      entry.level === "error"
                        ? "rgba(239,68,68,0.08)"
                        : entry.level === "warn"
                          ? "rgba(245,158,11,0.05)"
                          : entry.deltaMs > 5000
                            ? "rgba(239,68,68,0.06)"
                            : "transparent",
                  }}
                >
                  <td style={{ color: "#666" }}>{entry.seq}</td>
                  <td>
                    <span
                      style={{
                        color: levelColor(entry.level),
                        fontWeight: entry.level === "error" ? "bold" : "normal",
                        textTransform: "uppercase",
                        fontSize: "0.75rem",
                      }}
                    >
                      {entry.level}
                    </span>
                  </td>
                  <td style={{ fontFamily: "monospace" }}>
                    {entry.elapsedMs.toFixed(0)} ms
                  </td>
                  <td
                    style={{
                      fontFamily: "monospace",
                      fontWeight: entry.deltaMs > 2000 ? "bold" : "normal",
                      color: deltaColor(entry.deltaMs),
                    }}
                  >
                    +{entry.deltaMs.toFixed(0)}
                  </td>
                  <td style={{ fontSize: "0.75rem", color: "#999", whiteSpace: "nowrap" }}>
                    {entry.iso.replace("T", " ").replace("Z", "")}
                  </td>
                  <td style={{ fontFamily: "monospace", whiteSpace: "nowrap" }}>
                    {entry.label}
                  </td>
                  <td
                    style={{
                      maxWidth: 250,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      color: "#aaa",
                      fontSize: "0.75rem",
                    }}
                    title={entry.detail ? JSON.stringify(entry.detail) : ""}
                  >
                    {entry.detail ? JSON.stringify(entry.detail) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legend */}
      <div style={{ marginTop: 12, fontSize: "0.75rem", color: "var(--text-muted)" }}>
        <strong>Legend:</strong>{" "}
        <span style={{ color: "#6ee7b7" }}>●</span> Δ &lt; 500ms{" · "}
        <span style={{ color: "#fbbf24" }}>●</span> Δ &gt; 500ms{" · "}
        <span style={{ color: "#f59e0b" }}>●</span> Δ &gt; 2s{" · "}
        <span style={{ color: "#ef4444" }}>●</span> Δ &gt; 5s (likely bottleneck)
      </div>
    </div>
  );
}
