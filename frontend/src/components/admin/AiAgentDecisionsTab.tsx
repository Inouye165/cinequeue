import React, { useEffect, useState } from "react";
import { api } from "../../api";

interface AiAgentDecisionsTabProps {
  authToken?: string;
}

export const AiAgentDecisionsTab: React.FC<AiAgentDecisionsTabProps> = ({ authToken }) => {
  const [subTab, setSubTab] = useState<"logs" | "settings" | "prompts" | "preview">("logs");
  const [copiedMsg, setCopiedMsg] = useState<string | null>(null);

  // --- 1. Decision Logs State ---
  const [logs, setLogs] = useState<any[]>([]);
  const [totalLogs, setTotalLogs] = useState<number>(0);
  const [loadingLogs, setLoadingLogs] = useState<boolean>(false);
  const [selectedLog, setSelectedLog] = useState<any | null>(null);

  // Filters
  const [filterType, setFilterType] = useState<string>("");
  const [filterUser, setFilterUser] = useState<string>("");
  const [filterFallback, setFilterFallback] = useState<boolean>(false);

  // --- 2. Settings State ---
  const [config, setConfig] = useState<any | null>(null);
  const [configLoading, setConfigLoading] = useState<boolean>(false);
  const [configChangeNote, setConfigChangeNote] = useState<string>("");
  const [configSaveMsg, setConfigSaveMsg] = useState<string | null>(null);

  // --- 3. Prompt Manager State ---
  const [promptData, setPromptData] = useState<{ versions: any[]; active_version: any } | null>(null);
  const [systemInstruction, setSystemInstruction] = useState<string>("");
  const [wordingInstruction, setWordingInstruction] = useState<string>("");
  const [promptChangeNote, setPromptChangeNote] = useState<string>("");
  const [promptSaveMsg, setPromptSaveMsg] = useState<string | null>(null);

  // --- 4. Preview Simulator State ---
  const [previewWeather, setPreviewWeather] = useState<string>("Rain");
  const [previewAlert, setPreviewAlert] = useState<string>("");
  const [previewTitle, setPreviewTitle] = useState<string>("Spider-Man");
  const [previewIsStreaming, setPreviewIsStreaming] = useState<boolean>(true);
  const [previewTrivia, setPreviewTrivia] = useState<string>("");
  const [previewNews, setPreviewNews] = useState<string>("");
  const [previewInterest, setPreviewInterest] = useState<number>(0.85);
  const [previewSeed, setPreviewSeed] = useState<number>(42);
  const [previewResult, setPreviewResult] = useState<any | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);

  const showCopyToast = (msg: string) => {
    setCopiedMsg(msg);
    setTimeout(() => setCopiedMsg(null), 3000);
  };

  // --- Load Logs ---
  const fetchLogs = async () => {
    setLoadingLogs(true);
    try {
      const res = await api.adminAgentDecisionLogs(
        {
          limit: 30,
          user_id: filterUser || undefined,
          candidate_type: filterType || undefined,
          fallback_only: filterFallback || undefined,
        },
        authToken
      );
      setLogs(res.logs || []);
      setTotalLogs(res.total || 0);
    } catch (e: any) {
      console.error("Error loading decision logs:", e);
    } finally {
      setLoadingLogs(false);
    }
  };

  // --- Load Config ---
  const fetchConfig = async () => {
    setConfigLoading(true);
    try {
      const res = await api.adminAgentDecisionConfig(authToken);
      setConfig(res);
    } catch (e: any) {
      console.error("Error loading agent decision config:", e);
    } finally {
      setConfigLoading(false);
    }
  };

  // --- Load Prompts ---
  const fetchPrompts = async () => {
    try {
      const res = await api.adminAgentPromptVersions(authToken);
      setPromptData(res);
      if (res.active_version) {
        setSystemInstruction(res.active_version.system_instruction_template || "");
        setWordingInstruction(res.active_version.wording_instruction || "");
      }
    } catch (e: any) {
      console.error("Error loading prompt versions:", e);
    }
  };

  useEffect(() => {
    if (subTab === "logs") void fetchLogs();
    else if (subTab === "settings") void fetchConfig();
    else if (subTab === "prompts") void fetchPrompts();
  }, [subTab, filterType, filterUser, filterFallback]);

  // --- Handle Copy Diagnostics ---
  const copyToClipboard = (text: string, label: string) => {
    void navigator.clipboard.writeText(text);
    showCopyToast(`${label} copied.`);
  };

  const generateDiagnosticBundle = (log: any) => {
    return [
      `# CineQueue AI Agent Diagnostic Bundle`,
      `**Log ID**: ${log.log_id}`,
      `**Timestamp**: ${log.timestamp}`,
      `**User ID**: ${log.user_id}`,
      `**Model Requested**: ${log.model_requested}`,
      `**Model Used**: ${log.model_used || "None"}`,
      `**Provider**: ${log.fallback_used ? "Fallback Generator" : "Gemini API"}`,
      `**Fallback Reason**: ${log.fallback_reason || "None"}`,
      `**Duration**: ${log.request_duration_ms}ms`,
      ``,
      `## Decision Explanation`,
      `\`\`\`text`,
      log.selection_summary,
      `\`\`\``,
      ``,
      `## Selected Candidates`,
      `\`\`\`json`,
      JSON.stringify(log.selected_candidates, null, 2),
      `\`\`\``,
      ``,
      `## Cooldowns & Random Rolls`,
      `- Cooldowns: ${JSON.stringify(log.cooldowns_applied)}`,
      `- Random Rolls: ${JSON.stringify(log.random_rolls)}`,
      ``,
      `## Sanitized Prompt Sent to Gemini`,
      `\`\`\`text`,
      log.sanitized_prompt,
      `\`\`\``,
      ``,
      `## Raw Model Response`,
      `\`\`\`text`,
      log.raw_model_response,
      `\`\`\``,
      ``,
      `## Final Displayed Response`,
      `\`\`\`text`,
      log.final_response,
      `\`\`\``,
    ].join("\n");
  };

  // --- Config Save Handlers ---
  const handleSaveConfig = async () => {
    if (!config) return;
    try {
      const res = await api.adminUpdateAgentDecisionConfig(config, configChangeNote || "Updated decision settings", authToken);
      setConfig(res);
      setConfigSaveMsg("Decision configuration saved successfully.");
      setTimeout(() => setConfigSaveMsg(null), 3000);
    } catch (e: any) {
      alert(`Save Error: ${e.message}`);
    }
  };

  const handleResetConfig = async () => {
    if (!confirm("Are you sure you want to reset all decision settings to defaults?")) return;
    try {
      const res = await api.adminResetAgentDecisionConfig(authToken);
      setConfig(res);
      setConfigSaveMsg("Reset to default decision configuration.");
      setTimeout(() => setConfigSaveMsg(null), 3000);
    } catch (e: any) {
      alert(`Reset Error: ${e.message}`);
    }
  };

  // --- Prompt Save / Restore Handlers ---
  const handleSavePrompt = async () => {
    try {
      const res = await api.adminSaveAgentPromptVersion(systemInstruction, wordingInstruction, promptChangeNote || "Updated prompt wording", authToken);
      setPromptSaveMsg(`Prompt version ${res.version} saved.`);
      fetchPrompts();
      setTimeout(() => setPromptSaveMsg(null), 3000);
    } catch (e: any) {
      alert(`Prompt Save Error: ${e.message}`);
    }
  };

  const handleRestorePrompt = async (ver: number) => {
    if (!confirm(`Restore prompt version ${ver}?`)) return;
    try {
      await api.adminRestoreAgentPromptVersion(ver, authToken);
      fetchPrompts();
      showCopyToast(`Prompt version ${ver} restored.`);
    } catch (e: any) {
      alert(`Restore Error: ${e.message}`);
    }
  };

  // --- Preview Simulation ---
  const handleRunPreview = async () => {
    setPreviewLoading(true);
    try {
      const res = await api.adminPreviewAgentDecision(
        {
          user_id: "preview_admin_user",
          weather_condition: previewWeather || undefined,
          significant_alert: previewAlert || undefined,
          monitored_title_update: previewTitle || undefined,
          is_streaming_arrival: previewIsStreaming,
          trivia_fact: previewTrivia || undefined,
          major_news_title: previewNews || undefined,
          user_interest_score: previewInterest,
          random_seed: previewSeed,
        },
        authToken
      );
      setPreviewResult(res);
    } catch (e: any) {
      alert(`Preview Error: ${e.message}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div style={{ background: "var(--surface-color, #1a1a2e)", padding: "20px", borderRadius: "12px", color: "var(--text-color, #fff)" }}>
      {copiedMsg && (
        <div style={{ position: "fixed", bottom: "20px", right: "20px", background: "#4caf50", color: "#fff", padding: "12px 20px", borderRadius: "8px", zIndex: 10000, boxShadow: "0 4px 12px rgba(0,0,0,0.3)", fontWeight: "bold" }}>
          {copiedMsg}
        </div>
      )}

      {/* Sub-Navigation Header */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "20px", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "12px" }}>
        <button
          onClick={() => setSubTab("logs")}
          style={{ padding: "10px 18px", borderRadius: "6px", border: "none", background: subTab === "logs" ? "var(--primary-color, #e50914)" : "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer", fontWeight: "bold" }}
        >
          📊 Decision Logs ({totalLogs})
        </button>
        <button
          onClick={() => setSubTab("settings")}
          style={{ padding: "10px 18px", borderRadius: "6px", border: "none", background: subTab === "settings" ? "var(--primary-color, #e50914)" : "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer", fontWeight: "bold" }}
        >
          ⚙️ Agent Decision Settings
        </button>
        <button
          onClick={() => setSubTab("prompts")}
          style={{ padding: "10px 18px", borderRadius: "6px", border: "none", background: subTab === "prompts" ? "var(--primary-color, #e50914)" : "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer", fontWeight: "bold" }}
        >
          ✍️ Prompt Manager
        </button>
        <button
          onClick={() => setSubTab("preview")}
          style={{ padding: "10px 18px", borderRadius: "6px", border: "none", background: subTab === "preview" ? "var(--primary-color, #e50914)" : "rgba(255,255,255,0.08)", color: "#fff", cursor: "pointer", fontWeight: "bold" }}
        >
          🧪 Preview Simulator
        </button>
      </div>

      {/* --- SUBTAB 1: DECISION LOGS --- */}
      {subTab === "logs" && (
        <div>
          {/* Filters */}
          <div style={{ display: "flex", gap: "12px", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", background: "rgba(255,255,255,0.04)", padding: "12px", borderRadius: "8px" }}>
            <label style={{ fontSize: "0.9rem" }}>Candidate Type:</label>
            <select value={filterType} onChange={(e) => setFilterType(e.target.value)} style={{ padding: "6px 10px", borderRadius: "4px", background: "#2a2a40", color: "#fff", border: "1px solid #444" }}>
              <option value="">All Candidate Types</option>
              <option value="weather_alert">Severe Weather Alert</option>
              <option value="weather_viewing_connection">Weather Connection</option>
              <option value="personalized_trivia">Personalized Trivia</option>
              <option value="major_external_entertainment_news">External News</option>
              <option value="personalized_recommendation">Recommendation</option>
            </select>

            <label style={{ fontSize: "0.9rem" }}>User Filter:</label>
            <input type="text" placeholder="User ID..." value={filterUser} onChange={(e) => setFilterUser(e.target.value)} style={{ padding: "6px 10px", borderRadius: "4px", background: "#2a2a40", color: "#fff", border: "1px solid #444" }} />

            <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "0.9rem" }}>
              <input type="checkbox" checked={filterFallback} onChange={(e) => setFilterFallback(e.target.checked)} />
              Fallback Only
            </label>

            <button onClick={fetchLogs} style={{ padding: "6px 14px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>Refresh</button>
          </div>

          {/* Logs Table */}
          {loadingLogs ? (
            <p>Loading decision logs...</p>
          ) : logs.length === 0 ? (
            <p style={{ color: "#aaa" }}>No decision logs found matching filters.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.08)", textAlign: "left" }}>
                  <th style={{ padding: "10px" }}>Date & Time</th>
                  <th style={{ padding: "10px" }}>User</th>
                  <th style={{ padding: "10px" }}>Selected Type</th>
                  <th style={{ padding: "10px" }}>Model</th>
                  <th style={{ padding: "10px" }}>Provider</th>
                  <th style={{ padding: "10px" }}>Duration</th>
                  <th style={{ padding: "10px" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => {
                  const selTypes = l.selected_candidates?.map((c: any) => c.type).join(", ") || "None (Short Greeting)";
                  return (
                    <tr key={l.log_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                      <td style={{ padding: "10px" }}>{new Date(l.timestamp).toLocaleString()}</td>
                      <td style={{ padding: "10px" }}>{l.user_id}</td>
                      <td style={{ padding: "10px" }}>
                        <span style={{ background: l.selected_candidates?.length ? "#2e7d32" : "#555", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                          {selTypes}
                        </span>
                      </td>
                      <td style={{ padding: "10px" }}>{l.model_used || l.model_requested}</td>
                      <td style={{ padding: "10px" }}>
                        <span style={{ color: l.fallback_used ? "#ff9800" : "#4caf50" }}>
                          {l.fallback_used ? `Fallback (${l.fallback_reason})` : "Gemini API"}
                        </span>
                      </td>
                      <td style={{ padding: "10px" }}>{l.request_duration_ms}ms</td>
                      <td style={{ padding: "10px" }}>
                        <button onClick={() => setSelectedLog(l)} style={{ padding: "4px 10px", background: "#2196f3", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                          Inspect Log
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {/* Log Detail Drawer / Modal */}
          {selectedLog && (
            <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.8)", display: "flex", justifyContent: "center", alignItems: "center", zIndex: 9999 }}>
              <div style={{ background: "#1e1e30", width: "90%", maxWidth: "900px", maxHeight: "90vh", overflowY: "auto", padding: "24px", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.5)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid #333", paddingBottom: "12px" }}>
                  <h3>Log Detail: {selectedLog.log_id}</h3>
                  <button onClick={() => setSelectedLog(null)} style={{ background: "transparent", color: "#fff", border: "none", fontSize: "1.5rem", cursor: "pointer" }}>✕</button>
                </div>

                {/* Clipboard Actions Bar */}
                <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
                  <button onClick={() => copyToClipboard(generateDiagnosticBundle(selectedLog), "Markdown Diagnostic Bundle")} style={{ padding: "8px 14px", background: "#e50914", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}>
                    📋 Copy Full Diagnostic Bundle (Markdown)
                  </button>
                  <button onClick={() => copyToClipboard(selectedLog.selection_summary, "Explanation")} style={{ padding: "8px 14px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                    Copy Explanation
                  </button>
                  <button onClick={() => copyToClipboard(selectedLog.sanitized_prompt, "Sanitized Prompt")} style={{ padding: "8px 14px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                    Copy Prompt
                  </button>
                  <button onClick={() => copyToClipboard(selectedLog.raw_model_response, "Raw Response")} style={{ padding: "8px 14px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                    Copy Raw Response
                  </button>
                </div>

                {/* Explanation Card */}
                <div style={{ background: "rgba(255,255,255,0.04)", padding: "14px", borderRadius: "8px", marginBottom: "16px" }}>
                  <h4 style={{ margin: "0 0 8px" }}>Human-Readable Selection Explanation:</h4>
                  <pre style={{ whiteSpace: "pre-wrap", color: "#4caf50", margin: 0, fontFamily: "monospace" }}>{selectedLog.selection_summary}</pre>
                </div>

                {/* Candidates Evaluation Table */}
                <h4 style={{ marginBottom: "8px" }}>Candidates Evaluated:</h4>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", marginBottom: "16px" }}>
                  <thead>
                    <tr style={{ background: "rgba(255,255,255,0.08)", textAlign: "left" }}>
                      <th style={{ padding: "6px" }}>Title / Type</th>
                      <th style={{ padding: "6px" }}>Scores (Imp/Int/Nov/Conf = Comb)</th>
                      <th style={{ padding: "6px" }}>Status</th>
                      <th style={{ padding: "6px" }}>Reasons / Exclusion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...(selectedLog.selected_candidates || []), ...(selectedLog.excluded_candidates || [])].map((c: any, idx: number) => (
                      <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                        <td style={{ padding: "6px" }}>
                          <strong>{c.title}</strong>
                          <br />
                          <span style={{ fontSize: "0.75rem", color: "#aaa" }}>{c.type}</span>
                        </td>
                        <td style={{ padding: "6px" }}>
                          {c.importance_score} / {c.interest_score} / {c.novelty_score} / {c.confidence_score} = <strong>{c.combined_score}</strong>
                        </td>
                        <td style={{ padding: "6px" }}>
                          <span style={{ color: c.selected ? "#4caf50" : "#f44336" }}>{c.selected ? "SELECTED" : "EXCLUDED"}</span>
                        </td>
                        <td style={{ padding: "6px", fontSize: "0.8rem" }}>
                          {c.selected ? (c.interest_reasons?.join("; ") || "Selection criteria satisfied") : c.exclusion_reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Sanitized Prompt & Raw Response */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                  <div>
                    <h4 style={{ margin: "0 0 6px" }}>Sanitized Gemini Prompt:</h4>
                    <textarea readOnly value={selectedLog.sanitized_prompt} style={{ width: "100%", height: "120px", background: "#111", color: "#ddd", border: "1px solid #444", borderRadius: "4px", padding: "8px", fontSize: "0.8rem" }} />
                  </div>
                  <div>
                    <h4 style={{ margin: "0 0 6px" }}>Raw Gemini Response:</h4>
                    <textarea readOnly value={selectedLog.raw_model_response} style={{ width: "100%", height: "120px", background: "#111", color: "#ddd", border: "1px solid #444", borderRadius: "4px", padding: "8px", fontSize: "0.8rem" }} />
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* --- SUBTAB 2: SETTINGS --- */}
      {subTab === "settings" && config && (
        <div style={{ maxWidth: "800px" }}>
          {configSaveMsg && <p style={{ color: "#4caf50", fontWeight: "bold" }}>{configSaveMsg}</p>}

          <h3 style={{ borderBottom: "1px solid #333", paddingBottom: "8px" }}>Probabilities & Slot Control</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
            <div>
              <label>Optional Content Enabled:</label>
              <input type="checkbox" checked={config.optional_item_enabled} onChange={(e) => setConfig({ ...config, optional_item_enabled: e.target.checked })} style={{ marginLeft: "8px" }} />
            </div>
            <div>
              <label>Base Optional Probability (0-1):</label>
              <input type="number" step="0.05" value={config.optional_item_base_probability} onChange={(e) => setConfig({ ...config, optional_item_base_probability: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Weather Connection Prob:</label>
              <input type="number" step="0.05" value={config.weather_connection_probability} onChange={(e) => setConfig({ ...config, weather_connection_probability: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Trivia Prob:</label>
              <input type="number" step="0.05" value={config.trivia_probability} onChange={(e) => setConfig({ ...config, trivia_probability: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>External News Prob:</label>
              <input type="number" step="0.05" value={config.external_news_probability} onChange={(e) => setConfig({ ...config, external_news_probability: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Recommendation Prob:</label>
              <input type="number" step="0.05" value={config.recommendation_probability} onChange={(e) => setConfig({ ...config, recommendation_probability: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
          </div>

          <h3 style={{ borderBottom: "1px solid #333", paddingBottom: "8px" }}>Thresholds & Cooldowns</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px", marginBottom: "20px" }}>
            <div>
              <label>Min Interest Score:</label>
              <input type="number" step="0.05" value={config.minimum_interest_score} onChange={(e) => setConfig({ ...config, minimum_interest_score: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Min Combined Score:</label>
              <input type="number" step="0.05" value={config.minimum_combined_score} onChange={(e) => setConfig({ ...config, minimum_combined_score: parseFloat(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Weather Cooldown (Hours):</label>
              <input type="number" value={config.ordinary_weather_cooldown_hours} onChange={(e) => setConfig({ ...config, ordinary_weather_cooldown_hours: parseInt(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label>Trivia Cooldown (Hours):</label>
              <input type="number" value={config.trivia_cooldown_hours} onChange={(e) => setConfig({ ...config, trivia_cooldown_hours: parseInt(e.target.value) })} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label>Change Note:</label>
            <input type="text" placeholder="Explain why you are changing settings..." value={configChangeNote} onChange={(e) => setConfigChangeNote(e.target.value)} style={{ width: "100%", padding: "8px", background: "#222", color: "#fff", border: "1px solid #444" }} />
          </div>

          <div style={{ display: "flex", gap: "12px" }}>
            <button onClick={handleSaveConfig} style={{ padding: "10px 20px", background: "#4caf50", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: "bold" }}>Save Configuration</button>
            <button onClick={handleResetConfig} style={{ padding: "10px 20px", background: "#f44336", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer" }}>Reset Defaults</button>
          </div>
        </div>
      )}

      {/* --- SUBTAB 3: PROMPT MANAGER --- */}
      {subTab === "prompts" && (
        <div style={{ maxWidth: "900px" }}>
          {promptSaveMsg && <p style={{ color: "#4caf50", fontWeight: "bold" }}>{promptSaveMsg}</p>}

          <div style={{ marginBottom: "16px" }}>
            <h4 style={{ margin: "0 0 6px" }}>Wording Instruction (Editable by Admin):</h4>
            <textarea value={wordingInstruction} onChange={(e) => setWordingInstruction(e.target.value)} style={{ width: "100%", height: "140px", background: "#111", color: "#fff", border: "1px solid #444", borderRadius: "6px", padding: "10px" }} />
          </div>

          <div style={{ marginBottom: "16px" }}>
            <h4 style={{ margin: "0 0 6px" }}>System Instruction Template (Safety & Behavior Core):</h4>
            <textarea value={systemInstruction} onChange={(e) => setSystemInstruction(e.target.value)} style={{ width: "100%", height: "140px", background: "#111", color: "#ddd", border: "1px solid #444", borderRadius: "6px", padding: "10px" }} />
          </div>

          <div style={{ marginBottom: "16px" }}>
            <input type="text" placeholder="Change note (required to save)..." value={promptChangeNote} onChange={(e) => setPromptChangeNote(e.target.value)} style={{ width: "100%", padding: "8px", background: "#222", color: "#fff", border: "1px solid #444" }} />
          </div>

          <button onClick={handleSavePrompt} style={{ padding: "10px 20px", background: "#e50914", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", marginBottom: "24px" }}>
            Save New Prompt Version
          </button>

          {/* Prompt Version Timeline */}
          <h3>Prompt Version History</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {promptData?.versions?.map((v: any) => (
              <div key={v.version} style={{ background: "rgba(255,255,255,0.04)", padding: "12px", borderRadius: "8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong>Version {v.version}</strong> - <span style={{ color: "#aaa" }}>{new Date(v.updated_at).toLocaleString()} by {v.updated_by}</span>
                  <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "#ddd" }}>{v.change_note}</p>
                </div>
                {v.version !== promptData?.active_version?.version && (
                  <button onClick={() => handleRestorePrompt(v.version)} style={{ padding: "6px 12px", background: "#333", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                    Restore V{v.version}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* --- SUBTAB 4: PREVIEW SIMULATOR --- */}
      {subTab === "preview" && (
        <div style={{ maxWidth: "850px" }}>
          <h3>Deterministic Scenario Previewer</h3>
          <p style={{ color: "#aaa", fontSize: "0.9rem" }}>Simulate a startup briefing decision without presenting it to a user or modifying database presentation history.</p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "16px" }}>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Weather Condition:</label>
              <input type="text" value={previewWeather} onChange={(e) => setPreviewWeather(e.target.value)} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Severe Weather Alert (Mandatory):</label>
              <input type="text" placeholder="e.g. Severe Thunderstorm Warning" value={previewAlert} onChange={(e) => setPreviewAlert(e.target.value)} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Monitored Title Update:</label>
              <input type="text" value={previewTitle} onChange={(e) => setPreviewTitle(e.target.value)} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Trivia Candidate Fact:</label>
              <input type="text" placeholder="e.g. Filmed in Ireland rather than Scotland" value={previewTrivia} onChange={(e) => setPreviewTrivia(e.target.value)} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Major External News Title:</label>
              <input type="text" placeholder="e.g. Marvel Avengers Release" value={previewNews} onChange={(e) => setPreviewNews(e.target.value)} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
            <div>
              <label style={{ fontSize: "0.85rem" }}>Random Seed (Deterministic):</label>
              <input type="number" value={previewSeed} onChange={(e) => setPreviewSeed(parseInt(e.target.value))} style={{ width: "100%", padding: "6px", background: "#222", color: "#fff", border: "1px solid #444" }} />
            </div>
          </div>

          <button onClick={handleRunPreview} disabled={previewLoading} style={{ padding: "10px 20px", background: "#e50914", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", marginBottom: "20px" }}>
            {previewLoading ? "Running Simulation..." : "Run Preview Simulation"}
          </button>

          {previewResult && (
            <div style={{ background: "rgba(255,255,255,0.04)", padding: "16px", borderRadius: "8px" }}>
              <h4>Generated Greeting Output:</h4>
              <p style={{ color: "#4caf50", fontSize: "1.1rem", fontWeight: "bold", background: "#111", padding: "12px", borderRadius: "6px" }}>{previewResult.generated_greeting}</p>

              <h4>Decision Explanation:</h4>
              <pre style={{ whiteSpace: "pre-wrap", color: "#81c784", background: "#111", padding: "10px", borderRadius: "6px" }}>{previewResult.decision_log?.selection_summary}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
