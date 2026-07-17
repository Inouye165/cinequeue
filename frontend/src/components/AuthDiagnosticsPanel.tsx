import { useState, useEffect } from "react";
import {
  getActiveTrace,
  getTraceHistory,
  exportLatestTrace,
  AuthTrace,
  AuthTraceEvent,
} from "../utils/authPerformanceMonitor";

export function AuthDiagnosticsPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [trace, setTrace] = useState<AuthTrace | null>(null);
  const [history, setHistory] = useState<AuthTrace[]>([]);
  const [copied, setCopied] = useState(false);

  // Poll for updates every 1000ms in development/debug mode
  useEffect(() => {
    const updateData = () => {
      setTrace(getActiveTrace());
      setHistory(getTraceHistory());
    };
    updateData();
    const interval = setInterval(updateData, 1000);
    return () => clearInterval(interval);
  }, []);

  const debugEnabled =
    import.meta.env.VITE_AUTH_PERFORMANCE_DEBUG === "true" ||
    import.meta.env.DEV;

  if (!debugEnabled) {
    return null;
  }

  const handleCopy = () => {
    const json = exportLatestTrace();
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // Extract key duration helpers
  const getEventDuration = (events: AuthTraceEvent[], eventName: string): number | null => {
    const ev = events.find((e) => e.event === eventName);
    return ev?.durationMs || null;
  };

  const getSummaryMetrics = (currTrace: AuthTrace) => {
    const events = currTrace.events;
    const configDur = getEventDuration(events, "firebase_config_fetch_completed");
    const initDur = getEventDuration(events, "firebase_initialization_completed");
    const sessionDur = getEventDuration(events, "auth_state_callback_completed");
    const tokenDur = getEventDuration(events, "id_token_request_completed");
    const adminMeDur = getEventDuration(events, "admin_me_response_received");
    const uiUpdateDur = getEventDuration(events, "auth_context_state_update_completed");

    const tokenVerification = currTrace.backendTimings?.tokenVerificationMs ?? null;
    const adminLookup = currTrace.backendTimings?.adminLookupMs ?? null;

    // Total auth time is the time until auth loading is cleared or the last event
    const loadingClearedEvent = events.find((e) => e.event === "auth_loading_cleared");
    const totalTime = loadingClearedEvent 
      ? loadingClearedEvent.elapsedMs 
      : (events.length > 0 ? events[events.length - 1].elapsedMs : 0);

    return {
      configDur,
      initDur,
      sessionDur,
      tokenDur,
      adminMeDur,
      tokenVerification,
      adminLookup,
      uiUpdateDur,
      totalTime,
    };
  };

  const metrics = trace ? getSummaryMetrics(trace) : null;

  return (
    <div style={styles.floatingContainer}>
      {!isOpen ? (
        <button onClick={() => setIsOpen(true)} style={styles.badgeBtn}>
          ⏱️ Auth Diagnostics {trace?.warnings.length ? `(${trace.warnings.length}⚠️)` : ""}
        </button>
      ) : (
        <div style={styles.panel}>
          {/* Header */}
          <div style={styles.header}>
            <span style={styles.headerTitle}>⏱️ Authentication Tracing Dashboard</span>
            <button onClick={() => setIsOpen(false)} style={styles.closeBtn}>×</button>
          </div>

          <div style={styles.content}>
            {trace ? (
              <>
                <div style={styles.metaRow}>
                  <span><strong>Active Trace ID:</strong> {trace.traceId}</span>
                  <button onClick={handleCopy} style={styles.actionBtn}>
                    {copied ? "Copied! ✅" : "Copy Sanitized Trace"}
                  </button>
                </div>

                {/* Warnings Section */}
                {trace.warnings.length > 0 && (
                  <div style={styles.warningBox}>
                    <div style={styles.sectionHeader}>Warnings ({trace.warnings.length})</div>
                    <ul style={styles.warningList}>
                      {trace.warnings.map((w, idx) => (
                        <li key={idx} style={styles.warningItem}>⚠️ {w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Duration Summary */}
                {metrics && (
                  <div style={styles.card}>
                    <div style={styles.sectionHeader}>Duration Summary</div>
                    <div style={styles.summaryTable}>
                      <div style={styles.summaryRow}>
                        <span>Firebase config fetch:</span>
                        <span style={styles.valueText(metrics.configDur)}>
                          {metrics.configDur !== null ? `${metrics.configDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>Firebase initialization:</span>
                        <span style={styles.valueText(metrics.initDur)}>
                          {metrics.initDur !== null ? `${metrics.initDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>Session restoration:</span>
                        <span style={styles.valueText(metrics.sessionDur)}>
                          {metrics.sessionDur !== null ? `${metrics.sessionDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>ID token retrieval:</span>
                        <span style={styles.valueText(metrics.tokenDur)}>
                          {metrics.tokenDur !== null ? `${metrics.tokenDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>/api/admin/me network:</span>
                        <span style={styles.valueText(metrics.adminMeDur)}>
                          {metrics.adminMeDur !== null ? `${metrics.adminMeDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>Backend token verification:</span>
                        <span style={styles.valueText(metrics.tokenVerification)}>
                          {metrics.tokenVerification !== null ? `${metrics.tokenVerification.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>Backend admin lookup:</span>
                        <span style={styles.valueText(metrics.adminLookup)}>
                          {metrics.adminLookup !== null ? `${metrics.adminLookup.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={styles.summaryRow}>
                        <span>UI state update:</span>
                        <span style={styles.valueText(metrics.uiUpdateDur)}>
                          {metrics.uiUpdateDur !== null ? `${metrics.uiUpdateDur.toFixed(1)} ms` : "N/A"}
                        </span>
                      </div>
                      <div style={{ ...styles.summaryRow, borderTop: "1px solid #444", paddingTop: 8, marginTop: 4 }}>
                        <strong>Total authentication time:</strong>
                        <strong style={styles.valueText(metrics.totalTime, true)}>
                          {metrics.totalTime.toFixed(1)} ms
                        </strong>
                      </div>
                    </div>
                  </div>
                )}

                {/* Counts Summary */}
                <div style={styles.card}>
                  <div style={styles.sectionHeader}>Diagnostic Counts</div>
                  <div style={styles.grid}>
                    <div style={styles.gridItem}>Config Fetches: <strong>{trace.counts.configFetches}</strong></div>
                    <div style={styles.gridItem}>Init Attempts: <strong>{trace.counts.initAttempts}</strong></div>
                    <div style={styles.gridItem}>Listeners: <strong>{trace.counts.listenersRegistered}</strong></div>
                    <div style={styles.gridItem}>Callbacks: <strong>{trace.counts.callbacks}</strong></div>
                    <div style={styles.gridItem}>Get ID Tokens: <strong>{trace.counts.getIdTokenCalls}</strong></div>
                    <div style={styles.gridItem}>AdminMe Requests: <strong>{trace.counts.adminMeRequests}</strong></div>
                    <div style={styles.gridItem}>Popup Logins: <strong>{trace.counts.popupLogins}</strong></div>
                    <div style={styles.gridItem}>AuthProvider Mounts: <strong>{trace.counts.mounts}</strong></div>
                    <div style={styles.gridItem}>AuthProvider Cleanups: <strong>{trace.counts.cleanups}</strong></div>
                  </div>
                </div>

                {/* Chronological Table */}
                <div style={styles.card}>
                  <div style={styles.sectionHeader}>Chronological Events Log</div>
                  <div style={styles.tableWrapper}>
                    <table style={styles.table}>
                      <thead>
                        <tr style={styles.tableHeaderRow}>
                          <th style={styles.th}>Event</th>
                          <th style={styles.th}>Elapsed</th>
                          <th style={styles.th}>Duration</th>
                          <th style={styles.th}>Status</th>
                          <th style={styles.th}>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trace.events.map((e, idx) => (
                          <tr key={idx} style={styles.tableRow(e.durationMs)}>
                            <td style={styles.td}>{e.event}</td>
                            <td style={styles.td}>{e.elapsedMs.toFixed(1)} ms</td>
                            <td style={styles.td}>{e.durationMs ? `${e.durationMs.toFixed(1)} ms` : "-"}</td>
                            <td style={styles.td}>{e.status || "-"}</td>
                            <td style={styles.tdDetails}>
                              {e.details ? JSON.stringify(e.details) : "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : (
              <div style={styles.noTrace}>No active trace recorded yet. Start a login or session restoration flow.</div>
            )}

            {/* Trace History */}
            {history.length > 1 && (
              <div style={styles.card}>
                <div style={styles.sectionHeader}>Trace History</div>
                <div style={styles.historyList}>
                  {history.slice(0, -1).reverse().map((t, idx) => (
                    <div key={idx} style={styles.historyItem}>
                      <span>ID: {t.traceId}</span>
                      <span>Events: {t.events.length}</span>
                      <span>Warnings: {t.warnings.length}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  floatingContainer: {
    position: "fixed" as const,
    bottom: 20,
    right: 20,
    zIndex: 99999,
    fontFamily: "Outfit, Inter, sans-serif",
  },
  badgeBtn: {
    background: "rgba(30, 30, 40, 0.85)",
    backdropFilter: "blur(12px)",
    color: "#fff",
    border: "1px solid rgba(255, 255, 255, 0.15)",
    padding: "10px 16px",
    borderRadius: "24px",
    cursor: "pointer",
    boxShadow: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
    fontWeight: "bold" as const,
    transition: "all 0.2s ease",
  },
  panel: {
    width: "480px",
    maxHeight: "600px",
    background: "rgba(20, 20, 25, 0.95)",
    backdropFilter: "blur(20px)",
    color: "#e0e0e0",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "16px",
    boxShadow: "0 12px 40px 0 rgba(0, 0, 0, 0.5)",
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden",
  },
  header: {
    padding: "16px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "rgba(0, 0, 0, 0.2)",
  },
  headerTitle: {
    fontWeight: "bold" as const,
    fontSize: "15px",
    color: "#fff",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "#aaa",
    fontSize: "20px",
    cursor: "pointer",
    padding: 0,
    lineHeight: 1,
  },
  content: {
    padding: "16px",
    overflowY: "auto" as const,
    flex: 1,
  },
  metaRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "16px",
    fontSize: "12px",
  },
  actionBtn: {
    background: "#4f46e5",
    color: "#fff",
    border: "none",
    padding: "6px 12px",
    borderRadius: "6px",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: "bold" as const,
  },
  warningBox: {
    background: "rgba(239, 68, 68, 0.1)",
    border: "1px solid rgba(239, 68, 68, 0.3)",
    borderRadius: "8px",
    padding: "12px",
    marginBottom: "16px",
  },
  warningList: {
    margin: "8px 0 0 0",
    paddingLeft: "20px",
    fontSize: "12px",
    color: "#f87171",
  },
  warningItem: {
    marginBottom: "4px",
  },
  card: {
    background: "rgba(255, 255, 255, 0.03)",
    border: "1px solid rgba(255, 255, 255, 0.05)",
    borderRadius: "8px",
    padding: "12px",
    marginBottom: "16px",
  },
  sectionHeader: {
    fontWeight: "bold" as const,
    fontSize: "13px",
    color: "#fff",
    marginBottom: "8px",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
    paddingBottom: "4px",
  },
  summaryTable: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "6px",
    fontSize: "13px",
  },
  summaryRow: {
    display: "flex",
    justifyContent: "space-between",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap: "8px",
    fontSize: "12px",
  },
  gridItem: {
    background: "rgba(255, 255, 255, 0.01)",
    padding: "4px 8px",
    borderRadius: "4px",
  },
  tableWrapper: {
    overflowX: "auto" as const,
    maxHeight: "200px",
    overflowY: "auto" as const,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
    fontSize: "11px",
    textAlign: "left" as const,
  },
  tableHeaderRow: {
    borderBottom: "2px solid rgba(255, 255, 255, 0.1)",
  },
  th: {
    padding: "6px 8px",
    fontWeight: "bold" as const,
    color: "#aaa",
  },
  td: {
    padding: "6px 8px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
  },
  tdDetails: {
    padding: "6px 8px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
    color: "#888",
    whiteSpace: "nowrap" as const,
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: "150px",
  },
  noTrace: {
    textAlign: "center" as const,
    padding: "32px 0",
    color: "#888",
    fontSize: "13px",
  },
  historyList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "6px",
    fontSize: "11px",
    color: "#888",
  },
  historyItem: {
    display: "flex",
    justifyContent: "space-between",
    background: "rgba(0, 0, 0, 0.1)",
    padding: "4px 8px",
    borderRadius: "4px",
  },
  // Dynamic color function for metrics summary values
  valueText: (val: number | null, isBold = false) => {
    let color = "#e0e0e0";
    if (val !== null) {
      if (val > 1000) {
        color = "#ef4444"; // Red for >1s
      } else if (val > 500) {
        color = "#f59e0b"; // Amber for >500ms
      } else {
        color = "#10b981"; // Green for fast
      }
    }
    return {
      color,
      fontWeight: isBold ? "bold" : ("normal" as const),
    };
  },
  tableRow: (duration?: number) => {
    let background = "transparent";
    if (duration && duration > 1000) {
      background = "rgba(239, 68, 68, 0.08)";
    } else if (duration && duration > 500) {
      background = "rgba(245, 158, 11, 0.05)";
    }
    return {
      background,
    };
  },
};
