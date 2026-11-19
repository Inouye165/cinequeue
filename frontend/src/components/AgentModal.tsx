import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { movieService, normalizePosterPath } from "../services/movieService";
import { cancelSpeech, speakSpeechText } from "../utils/speech";
import { syncService } from "../services/syncService";
import { StarRating } from "./StarRating";
import { ActionConfirmationModal, type PendingActionItem } from "./ActionConfirmationModal";
import type { AgentLogsResponse, AgentSettings, ChatMessage, PersonalityPreset, RatedMovie } from "../types";


interface AgentModalProps {
  ownerId: string;
  isOpen: boolean;
  onClose: () => void;
  onWatchlistUpdated?: () => void;
  initialTab?: "chat" | "settings" | "logs";
}

const PRESETS: { id: PersonalityPreset; name: string; icon: string; desc: string }[] = [
  { id: "cinephile", name: "Cinephile Critic", icon: "🎬", desc: "Passionate, knowledgeable movie & TV enthusiast with witty insights." },
  { id: "noir", name: "Film Noir Detective", icon: "🕵️", desc: "Cynical 1940s detective viewing your queue through rain-slicked streets." },
  { id: "scifi", name: "Sci-Fi AI", icon: "🤖", desc: "Crisp, precise futuristic AI unit managing media telemetry archives." },
  { id: "sarcastic", name: "Sarcastic Buddy", icon: "😼", desc: "Hilarious, sarcastic friend who gives great advice with playful jabs." },
  { id: "custom", name: "Custom Persona", icon: "✍️", desc: "Define your own unique AI system instructions and tone." },
];

const SUGGESTIONS = [
  "🎲 Quiz me on 5 movies!",
  "⭐️ What movies have I rated?",
  "🎬 Recommend a free movie to stream",
  "What updates do I have on my monitored shows?",
  "Notify me when Oppenheimer drops under $4 to rent",
];


export function AgentModal({ ownerId, isOpen, onClose, onWatchlistUpdated, initialTab = "chat" }: AgentModalProps) {
  const [activeTab, setActiveTab] = useState<"chat" | "settings" | "logs">(initialTab);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);
  const [quizRatings, setQuizRatings] = useState<Record<number, number>>({});
  const [logsData, setLogsData] = useState<AgentLogsResponse | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    void navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const copyAllLogsJSON = () => {
    if (!logsData) return;
    const fullJSON = JSON.stringify(logsData.logs, null, 2);
    copyToClipboard(fullJSON, "all-logs");
  };

  const persistLocalMutation = async (params: {
    tmdbId: number;
    mediaType?: string | null;
    title: string;
    posterPath?: string | null;
    releaseDate?: string | null;
    status?: "queue" | "following" | "library" | "watched";
    watchStatus?: "unwatched" | "watching" | "watched";
    rating?: number | null;
  }) => {
    if (!params.tmdbId || params.tmdbId <= 0) return;
    await movieService.saveMovie(
      {
        tmdbId: params.tmdbId,
        mediaType: params.mediaType === "tv" ? "tv" : "movie",
        title: params.title,
        posterPath: normalizePosterPath(params.posterPath),
        releaseDate: params.releaseDate ?? undefined,
        status: params.status,
        watchStatus: params.watchStatus,
        rating: params.rating,
      },
      ownerId
    );
    if (ownerId !== "guest_local") {
      void syncService.triggerSync(ownerId);
    }
  };

  const handleRateQuizMovie = async (movie: RatedMovie, rating: number) => {
    if (!movie.tmdb_id || movie.tmdb_id <= 0) return;
    setQuizRatings((prev) => ({ ...prev, [movie.tmdb_id]: rating }));
    try {
      await persistLocalMutation({
        tmdbId: movie.tmdb_id,
        mediaType: movie.media_type,
        title: movie.title,
        posterPath: movie.poster_path,
        releaseDate: movie.release_date,
        rating,
        ...(rating === 0 ? { watchStatus: "unwatched" } : { status: "watched", watchStatus: "watched" }),
      });
      onWatchlistUpdated?.();
    } catch (err) {
      console.error("Failed to save quiz rating:", err);
    }
  };


  const [settings, setSettings] = useState<AgentSettings>({
    personality_preset: "cinephile",
    custom_prompt: "",
    location: "",
    notify_on_login: true,
    auto_add_mentioned: true,
    track_price_drops: true,
    auto_speak_briefing: false,
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSavedToast, setSettingsSavedToast] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      void loadChatHistory();
      void loadSettings();
      if (initialTab === "logs") {
        void loadLogs();
      }
    }
  }, [isOpen, initialTab]);

  useEffect(() => {
    if (isOpen && activeTab === "logs") {
      void loadLogs();
    }
  }, [isOpen, activeTab]);

  const loadLogs = async () => {
    setLoadingLogs(true);
    try {
      const data = await api.getAgentLogs(50);
      setLogsData(data);
    } catch (err) {
      console.error("Failed to load agent telemetry logs:", err);
    } finally {
      setLoadingLogs(false);
    }
  };

  useEffect(() => {
    if (activeTab === "chat") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, activeTab]);

  const loadChatHistory = async () => {
    setLoadingChat(true);
    try {
      const data = await api.agentChatHistory();
      setMessages(data);
    } catch (err) {
      console.error("Failed to load chat history:", err);
    } finally {
      setLoadingChat(false);
    }
  };

  const loadSettings = async () => {
    try {
      const data = await api.agentSettings();
      setSettings(data);
    } catch (err) {
      console.error("Failed to load agent settings:", err);
    }
  };

  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingConfirmItems, setPendingConfirmItems] = useState<PendingActionItem[]>([]);

  const handleConfirmBatchActions = async (confirmedItems: PendingActionItem[]) => {
    for (const item of confirmedItems) {
      if (!item.tmdb_id || item.tmdb_id <= 0) continue;
      if (item.action_type === "rate_movie") {
        await persistLocalMutation({
          tmdbId: item.tmdb_id,
          mediaType: item.media_type,
          title: item.title,
          rating: item.rating,
          status: "watched",
          watchStatus: "watched",
          posterPath: item.poster_path,
          releaseDate: item.release_date,
        });
      } else {
        await persistLocalMutation({
          tmdbId: item.tmdb_id,
          mediaType: item.media_type,
          title: item.title,
          status: "queue",
          posterPath: item.poster_path,
          releaseDate: item.release_date,
        });
      }
    }
    onWatchlistUpdated?.();
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || sending) return;

    setInputMessage("");
    setSending(true);

    // Optimistic user message addition
    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const res = await api.sendAgentChatMessage(text);
      setMessages((prev) => [...prev, res.message]);
      if (res.actions_taken && res.actions_taken.length > 0) {
        const proposed: PendingActionItem[] = res.actions_taken
          .filter((a: any) => a.action === "rate_movie" || a.action === "add_monitoring")
          .map((a: any, idx: number) => ({
            id: `act_${Date.now()}_${idx}`,
            tmdb_id: a.tmdb_id,
            media_type: a.media_type || "movie",
            title: a.title,
            poster_path: a.poster_path,
            release_date: a.release_date,
            rating: a.rating || 5,
            action_type: a.action,
            checked: true,
          }));

        if (proposed.length > 0) {
          setPendingConfirmItems(proposed);
          setShowConfirmModal(true);
        }
        onWatchlistUpdated?.();
      }
    } catch (err) {
      console.error("Failed to send chat message:", err);
      const errMsg: ChatMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: "Sorry, I had trouble processing that. Please try again!",
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setSending(false);
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Clear all conversation history with your AI Agent?")) return;
    try {
      await api.clearAgentChatHistory();
      setMessages([]);
    } catch (err) {
      console.error("Failed to clear chat history:", err);
    }
  };

  const handleSaveSettings = async (settingsToSave?: AgentSettings) => {
    const payload = settingsToSave && "personality_preset" in settingsToSave ? settingsToSave : settings;
    setSavingSettings(true);
    try {
      const updated = await api.saveAgentSettings(payload);
      setSettings(updated);
      setSettingsSavedToast(true);
      setTimeout(() => setSettingsSavedToast(false), 3000);
    } catch (err) {
      alert("Failed to save settings: " + (err instanceof Error ? err.message : "Unknown error"));
    } finally {
      setSavingSettings(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="agent-modal-backdrop" onClick={onClose}>
      <div className="agent-modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="mobile-sheet-handle" aria-hidden="true" />
        {/* Header */}
        <div className="agent-modal-header">
          <div className="agent-modal-title">
            <span className="agent-avatar-icon">🤖</span>
            <div>
              <h3>Cinequeue AI Agent</h3>
              <p className="agent-subtitle">
                {settings.personality_preset === "custom"
                  ? "Custom Persona"
                  : PRESETS.find((p) => p.id === settings.personality_preset)?.name || "Cinephile Critic"}
              </p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}>&times;</button>
        </div>

        {/* Navigation Tabs */}
        <div className="agent-modal-tabs">
          <button
            className={`agent-tab-btn ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            💬 Chat Memory
          </button>
          <button
            className={`agent-tab-btn ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => setActiveTab("settings")}
          >
            ⚙️ Personality & Settings
          </button>
          <button
            className={`agent-tab-btn ${activeTab === "logs" ? "active" : ""}`}
            onClick={() => setActiveTab("logs")}
          >
            📊 AI Usage & Telemetry Logs
          </button>
        </div>

        {/* Content Body */}
        <div className="agent-modal-body">
          {activeTab === "chat" ? (
            <div className="agent-chat-view">
              {settings.ai_calls_enabled === false && (
                <div
                  style={{
                    padding: "8px 12px",
                    marginBottom: "8px",
                    borderRadius: "8px",
                    backgroundColor: "rgba(234, 179, 8, 0.12)",
                    border: "1px solid rgba(234, 179, 8, 0.3)",
                    color: "#fef08a",
                    fontSize: "0.82rem",
                    lineHeight: "1.4",
                  }}
                >
                  ⚡ <strong>AI API Calls Disabled (Dev Mode)</strong>: External AI calls are currently paused to save API costs (<code>ENABLE_AI_CALLS=false</code>). Instant deterministic fallbacks are active.
                </div>
              )}
              {/* Messages Area */}
              <div className="agent-messages-container">
                {loadingChat ? (
                  <div className="agent-loading">Loading memory history…</div>
                ) : messages.length === 0 ? (
                  <div className="agent-empty-chat">
                    <p className="empty-title">👋 Hello! I'm your Cinequeue AI Agent.</p>
                    <p>I monitor your shows, track price drops, and remember your taste!</p>
                    <div className="suggestions-prompt">Try asking:</div>
                    <div className="suggestions-list">
                      {SUGGESTIONS.map((s, idx) => (
                        <button key={idx} className="suggestion-chip" onClick={() => void handleSendMessage(s)}>
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <>
                    {messages.map((msg, index) => (
                      <div key={msg.id || index} className={`chat-bubble-wrapper ${msg.role}`}>
                        <div className="chat-avatar">{msg.role === "user" ? "👤" : "🤖"}</div>
                        <div className="chat-bubble">
                          <div className="chat-content">{msg.content}</div>
                          {msg.actions && msg.actions.length > 0 ? (
                            <div className="chat-actions-list" style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "10px" }}>
                              {msg.actions.map((act, aIdx) => {
                                if (act.action === "movie_quiz" && act.movies) {
                                  return (
                                    <div key={aIdx} className="quiz-container-card" style={{ background: "rgba(0, 0, 0, 0.4)", borderRadius: "8px", padding: "12px", border: "1px solid rgba(255, 184, 0, 0.4)" }}>
                                      <h4 style={{ margin: "0 0 10px 0", color: "#FFB800", fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "6px" }}>
                                        <span>🎲</span> 5-Movie Quiz — Have you seen these?
                                      </h4>
                                      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                                        {act.movies.map((m) => {
                                          const currentRating = quizRatings[m.tmdb_id] !== undefined ? quizRatings[m.tmdb_id] : (m.rating || 0);
                                          return (
                                            <div key={m.tmdb_id} style={{ display: "flex", alignItems: "center", gap: "10px", background: "rgba(255, 255, 255, 0.05)", padding: "8px", borderRadius: "6px" }}>
                                              {m.poster_url ? (
                                                <img src={m.poster_url} alt={m.title} style={{ width: "40px", height: "60px", objectFit: "cover", borderRadius: "4px" }} />
                                              ) : (
                                                <div style={{ width: "40px", height: "60px", background: "#333", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px", textAlign: "center" }}>{m.title}</div>
                                              )}
                                              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
                                                <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "#fff" }}>{m.title}</span>
                                                {m.release_date ? <span style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.5)" }}>{m.release_date.slice(0, 4)}</span> : null}
                                                <StarRating
                                                  rating={currentRating}
                                                  onRate={(r) => void handleRateQuizMovie(m, r)}
                                                  size="sm"
                                                />
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  );
                                }
                                if (act.action === "streaming_recommendation") {
                                  return (
                                    <div key={aIdx} className="recommendation-card" style={{ background: "rgba(0, 0, 0, 0.4)", borderRadius: "8px", padding: "12px", border: "1px solid rgba(0, 229, 255, 0.4)", display: "flex", gap: "12px", alignItems: "center" }}>
                                      {act.poster_url ? (
                                        <img src={act.poster_url} alt={act.title || "Movie"} style={{ width: "50px", height: "75px", objectFit: "cover", borderRadius: "4px" }} />
                                      ) : null}
                                      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                                        <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#fff" }}>🎬 {act.title}</span>
                                        <span style={{ fontSize: "0.85rem", color: "#00E5FF", fontWeight: 600 }}>{act.details_text}</span>
                                        {act.overview ? <span style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.7)" }}>{act.overview}</span> : null}
                                        {act.tmdb_id ? (
                                          <button
                                            type="button"
                                            style={{ alignSelf: "flex-start", marginTop: "4px", padding: "4px 10px", fontSize: "0.75rem", borderRadius: "4px", background: "#FFB800", color: "#000", border: "none", cursor: "pointer", fontWeight: 600 }}
                                            onClick={async () => {
                                              if (act.tmdb_id && act.tmdb_id > 0 && act.title) {
                                                await persistLocalMutation({
                                                  tmdbId: act.tmdb_id,
                                                  mediaType: act.media_type,
                                                  title: act.title,
                                                  posterPath: act.poster_url,
                                                  releaseDate: act.release_date,
                                                  status: "queue",
                                                });
                                                onWatchlistUpdated?.();
                                              }
                                            }}
                                          >
                                            ➕ Add to Queue
                                          </button>
                                        ) : null}
                                      </div>
                                    </div>
                                  );
                                }
                                if (act.action === "rate_movie") {
                                  return (
                                    <div key={aIdx} className="recommendation-card" style={{ background: "rgba(0, 0, 0, 0.4)", borderRadius: "8px", padding: "12px", border: "1px solid rgba(255, 184, 0, 0.5)", display: "flex", gap: "12px", alignItems: "center" }}>
                                      {act.poster_url ? (
                                        <img src={act.poster_url} alt={act.title || "Movie"} style={{ width: "50px", height: "75px", objectFit: "cover", borderRadius: "4px" }} />
                                      ) : null}
                                      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "4px" }}>
                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                          <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#fff" }}>⭐️ {act.title}</span>
                                          <span style={{ fontSize: "0.75rem", background: "rgba(255, 184, 0, 0.2)", color: "#FFB800", padding: "2px 8px", borderRadius: "4px" }}>Rated & Watched</span>
                                        </div>
                                        {act.release_date ? <span style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.5)" }}>{act.release_date.slice(0, 4)}</span> : null}
                                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "2px" }}>
                                          <StarRating rating={act.rating || 5} onRate={() => {}} size="sm" />
                                          <span style={{ fontSize: "0.85rem", color: "#FFB800", fontWeight: 600 }}>{act.rating || 5}/5 stars</span>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                }
                                if (act.action === "movie_search" && act.results) {
                                  return (
                                    <div key={aIdx} className="quiz-container-card" style={{ background: "rgba(0, 0, 0, 0.4)", borderRadius: "8px", padding: "12px", border: "1px solid rgba(0, 229, 255, 0.4)" }}>
                                      <h4 style={{ margin: "0 0 10px 0", color: "#00E5FF", fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "6px" }}>
                                        <span>🔍</span> Search Results for "{act.query}"
                                      </h4>
                                      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                                        {act.results.map((r) => (
                                          <div key={r.tmdb_id} style={{ display: "flex", alignItems: "center", gap: "10px", background: "rgba(255, 255, 255, 0.05)", padding: "8px", borderRadius: "6px" }}>
                                            {r.poster_url ? (
                                              <img src={r.poster_url} alt={r.title} style={{ width: "40px", height: "60px", objectFit: "cover", borderRadius: "4px" }} />
                                            ) : (
                                              <div style={{ width: "40px", height: "60px", background: "#333", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px", textAlign: "center" }}>{r.title}</div>
                                            )}
                                            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
                                              <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "#fff" }}>{r.title}</span>
                                              {r.release_date ? <span style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.5)" }}>{r.release_date.slice(0, 4)}</span> : null}
                                              <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                                                <button
                                                  type="button"
                                                  style={{ padding: "3px 8px", fontSize: "0.7rem", borderRadius: "4px", background: "#FFB800", color: "#000", border: "none", cursor: "pointer", fontWeight: 600 }}
                                                  onClick={async () => {
                                                    await persistLocalMutation({
                                                      tmdbId: r.tmdb_id,
                                                      mediaType: r.media_type,
                                                      title: r.title,
                                                      rating: 5,
                                                      status: "watched",
                                                      watchStatus: "watched",
                                                      posterPath: r.poster_path,
                                                      releaseDate: r.release_date,
                                                    });
                                                    onWatchlistUpdated?.();
                                                  }}
                                                >
                                                  ⭐️ Rate 5★
                                                </button>
                                                <button
                                                  type="button"
                                                  style={{ padding: "3px 8px", fontSize: "0.7rem", borderRadius: "4px", background: "rgba(255, 255, 255, 0.15)", color: "#fff", border: "none", cursor: "pointer", fontWeight: 600 }}
                                                  onClick={async () => {
                                                    await persistLocalMutation({
                                                      tmdbId: r.tmdb_id,
                                                      mediaType: r.media_type,
                                                      title: r.title,
                                                      status: "queue",
                                                      posterPath: r.poster_path,
                                                      releaseDate: r.release_date,
                                                    });
                                                    onWatchlistUpdated?.();
                                                  }}
                                                >
                                                  ➕ Add to Queue
                                                </button>
                                              </div>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  );
                                }
                                return (
                                  <div key={aIdx} className="chat-action-tag">
                                    {act.action === "add_monitoring" || act.action === "update_monitoring"
                                      ? `🎯 Added "${act.title}" to Monitoring`
                                      : act.action === "update_status"
                                      ? `📌 Updated status of "${act.title}" to ${act.status || "updated"}`
                                      : act.action === "delete_rating"
                                      ? `🗑️ Deleted rating for "${act.title}"`
                                      : act.action === "remove_item"
                                      ? `🗑️ Removed "${act.title}" from Queue`
                                      : `💲 Rental Target set to $${act.target_rental_price?.toFixed(2)}`}
                                  </div>
                                );
                              })}
                            </div>
                          ) : null}

                          <div className="chat-bubble-footer">
                            {msg.role === "assistant" ? (
                              <button
                                className="speak-bubble-btn"
                                onClick={() => {
                                  cancelSpeech();
                                  speakSpeechText(msg.content);
                                }}
                                title="Listen out loud"
                              >
                                🔊 Listen
                              </button>
                            ) : null}
                            {msg.created_at ? (
                              <span className="chat-time">
                                {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ))}
                    {sending ? (
                      <div className="chat-bubble-wrapper assistant">
                        <div className="chat-avatar">🤖</div>
                        <div className="chat-bubble typing-indicator">
                          <span>.</span><span>.</span><span>.</span>
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Chat Input */}
              <div className="agent-chat-footer">
                {messages.length > 0 ? (
                  <button className="clear-history-link" onClick={handleClearHistory}>
                    Clear history
                  </button>
                ) : null}
                <form
                  className="chat-input-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void handleSendMessage();
                  }}
                >
                  <input
                    type="text"
                    placeholder="Ask about movies, add titles to monitoring, or set price targets..."
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    disabled={sending}
                  />
                  <button type="submit" disabled={!inputMessage.trim() || sending} className="chat-send-btn">
                    Send
                  </button>
                </form>
              </div>
            </div>
          ) : activeTab === "settings" ? (
            <div className="agent-settings-view">
              <h4>Choose AI Personality</h4>
              <p className="settings-desc">Select how your agent talks and interacts with you across Cinequeue.</p>

              <div className="preset-grid">
                {PRESETS.map((p) => (
                  <div
                    key={p.id}
                    className={`preset-card ${settings.personality_preset === p.id ? "selected" : ""}`}
                    onClick={() => setSettings((prev) => ({ ...prev, personality_preset: p.id }))}
                  >
                    <div className="preset-icon">{p.icon}</div>
                    <div className="preset-info">
                      <div className="preset-name">{p.name}</div>
                      <div className="preset-desc">{p.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              {settings.personality_preset === "custom" ? (
                <div className="custom-prompt-group">
                  <label>Custom System Prompt</label>
                  <textarea
                    rows={3}
                    placeholder="e.g., You are a futuristic starship AI named Jarvis who speaks politely and loves sci-fi movies..."
                    value={settings.custom_prompt || ""}
                    onChange={(e) => setSettings((prev) => ({ ...prev, custom_prompt: e.target.value }))}
                  />
                </div>
              ) : null}

              <div className="custom-prompt-group">
                <label>📍 User Location (City or Zip Code)</label>
                <input
                  type="text"
                  placeholder="e.g., New York, NY or 10001"
                  value={settings.location || ""}
                  onChange={(e) => setSettings((prev) => ({ ...prev, location: e.target.value }))}
                  onBlur={() => void handleSaveSettings()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void handleSaveSettings();
                    }
                  }}
                  style={{
                    width: "100%",
                    background: "rgba(0, 0, 0, 0.2)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    padding: "10px",
                    color: "var(--text)",
                    fontSize: "0.88rem",
                  }}
                />
                <span className="toggle-sub" style={{ marginTop: "4px", display: "block" }}>
                  Used to fetch real-time local weather reports to influence your AI agent's mood and recommendations.
                </span>
              </div>
              <hr className="settings-divider" />

              <h4>Agent Automation & Capabilities</h4>
              <div className="automation-toggles">
                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={settings.notify_on_login}
                    onChange={(e) => setSettings((prev) => ({ ...prev, notify_on_login: e.target.checked }))}
                  />
                  <div className="toggle-text">
                    <span className="toggle-label">🔔 Login Briefing Banner</span>
                    <span className="toggle-sub">Evaluate monitored titles and show persona update briefing on login</span>
                  </div>
                </label>

                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={settings.auto_add_mentioned}
                    onChange={(e) => setSettings((prev) => ({ ...prev, auto_add_mentioned: e.target.checked }))}
                  />
                  <div className="toggle-text">
                    <span className="toggle-label">🎯 Auto-add Mentioned Titles</span>
                    <span className="toggle-sub">When you say you are waiting for a movie/show in chat, automatically monitor it</span>
                  </div>
                </label>

                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={settings.track_price_drops}
                    onChange={(e) => setSettings((prev) => ({ ...prev, track_price_drops: e.target.checked }))}
                  />
                  <div className="toggle-text">
                    <span className="toggle-label">🏷️ Rental Price Drop Alerts</span>
                    <span className="toggle-sub">Detect dollar price targets in chat and notify you when rental prices drop</span>
                  </div>
                </label>

                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={Boolean(settings.auto_speak_briefing)}
                    onChange={(e) => setSettings((prev) => ({ ...prev, auto_speak_briefing: e.target.checked }))}
                  />
                  <div className="toggle-text">
                    <span className="toggle-label">🔊 Auto-Speak Login Briefing</span>
                    <span className="toggle-sub">Automatically read your startup briefing aloud when it appears</span>
                  </div>
                </label>
              </div>

              <div className="settings-actions">
                {settingsSavedToast ? <span className="saved-toast">✓ Settings saved!</span> : <span />}
                <button className="save-settings-btn" onClick={() => void handleSaveSettings()} disabled={savingSettings}>
                  {savingSettings ? "Saving…" : "Save Agent Settings"}
                </button>
              </div>
            </div>
          ) : activeTab === "logs" ? (
            <div className="agent-logs-view">
              {/* Summary statistics grid */}
              <div className="logs-summary-grid">
                <div className="logs-summary-card">
                  <div className="card-top-row">
                    <span className="label">Total Calls</span>
                    <span className="card-badge info">API</span>
                  </div>
                  <span className="value">{logsData?.summary?.total_calls ?? 0}</span>
                </div>
                <div className="logs-summary-card">
                  <div className="card-top-row">
                    <span className="label">Avg Latency</span>
                    <span className="card-badge speed">Fast</span>
                  </div>
                  <span className="value">{logsData?.summary?.avg_duration_ms ?? 0} ms</span>
                </div>
                <div className="logs-summary-card">
                  <div className="card-top-row">
                    <span className="label">Success Rate</span>
                    <span className="card-badge success">100%</span>
                  </div>
                  <span className="value">{logsData?.summary?.success_rate_percent ?? 100}%</span>
                </div>
                <div className="logs-summary-card">
                  <div className="card-top-row">
                    <span className="label">Fallbacks</span>
                    <span className={`card-badge ${(logsData?.summary?.fallback_count || 0) > 0 ? "warning" : "healthy"}`}>
                      {(logsData?.summary?.fallback_count || 0) > 0 ? "Alert" : "Healthy"}
                    </span>
                  </div>
                  <span className="value" style={{ color: (logsData?.summary?.fallback_count || 0) > 0 ? "var(--danger)" : "#4285f4" }}>
                    {logsData?.summary?.fallback_count ?? 0}
                  </span>
                </div>
              </div>

              <div className="logs-header-bar">
                <div className="logs-header-title">
                  <span className="g-icon">⚙️</span>
                  <h4>AI Developer Telemetry & Debug Logs</h4>
                </div>
                <div className="logs-header-actions">
                  <button
                    className="copy-btn secondary-btn"
                    onClick={copyAllLogsJSON}
                    disabled={!logsData || logsData.logs.length === 0}
                    title="Copy all telemetry logs as formatted JSON to clipboard"
                  >
                    {copiedId === "all-logs" ? "✓ All Logs Copied!" : "📋 Copy All Logs"}
                  </button>
                  <button
                    className="save-settings-btn"
                    style={{ padding: "6px 12px", fontSize: "0.82rem" }}
                    onClick={() => void loadLogs()}
                    disabled={loadingLogs}
                  >
                    {loadingLogs ? "Refreshing…" : "🔄 Refresh"}
                  </button>
                </div>
              </div>

              {loadingLogs && !logsData ? (
                <div className="agent-loading">Fetching AI telemetry logs…</div>
              ) : !logsData || logsData.logs.length === 0 ? (
                <div className="agent-empty-chat">
                  <p className="empty-title">📋 No AI Telemetry Logs Found</p>
                  <p>Interact with the AI Agent in chat or trigger a briefing to generate usage logs!</p>
                </div>
              ) : (
                <div className="logs-list">
                  {logsData.logs.map((log) => {
                    const isCopied = copiedId === log.log_id;
                    const promptCopied = copiedId === `prompt-${log.log_id}`;
                    const respCopied = copiedId === `resp-${log.log_id}`;

                    return (
                      <div key={log.log_id} className="log-entry-card">
                        <div className="log-entry-header">
                          <div className="header-chips">
                            <span className={`status-pill ${!log.gemini_called ? "local" : (log.fallback_used ? "fallback" : (log.event_type && log.event_type.includes("failed") ? "failed" : "success"))}`}>
                              {!log.gemini_called ? "🧠 Local Event" : (log.fallback_used ? "⚠️ Fallback" : (log.event_type && log.event_type.includes("failed") ? "❌ Error" : "⚡ 200 OK"))}
                            </span>
                            <span className="chip event-chip">{log.event_type}</span>
                            <span className="chip model-chip">{log.gemini_called ? (log.model_used || log.model_requested || "gemini-3.6-flash") : (log.daily_cache_key ? `Cache Key: ${log.daily_cache_key}` : "N/A (Local)")}</span>
                            <span className="chip latency-chip">
                              {log.request_duration_ms != null ? `${log.request_duration_ms} ms` : "N/A"}
                            </span>
                          </div>

                          <div className="header-right">
                            <span className="timestamp-text">
                              {new Date(log.timestamp).toLocaleString()}
                            </span>
                            <button
                              className="icon-copy-btn"
                              onClick={() => copyToClipboard(JSON.stringify(log, null, 2), log.log_id)}
                              title="Copy log entry JSON"
                            >
                              {isCopied ? "✓ Copied" : "📋 Copy Log"}
                            </button>
                          </div>
                        </div>

                        {log.selection_summary ? (
                          <div className="log-entry-summary">
                            <div className="summary-label">Selection Summary / Telemetry:</div>
                            <div className="summary-content">{log.selection_summary}</div>
                          </div>
                        ) : null}

                        {log.sanitized_prompt ? (
                          <details className="payload-inspector">
                            <summary className="inspector-summary">
                              <span>🔍 View Prompt & Response Payload</span>
                              <span className="expand-icon">▶</span>
                            </summary>
                            <div className="inspector-content">
                              <div className="payload-block">
                                <div className="block-header">
                                  <span>Prompt Sent to Gemini</span>
                                  <button
                                    className="mini-copy-btn"
                                    onClick={() => copyToClipboard(log.sanitized_prompt || "", `prompt-${log.log_id}`)}
                                  >
                                    {promptCopied ? "✓ Copied!" : "📋 Copy Prompt"}
                                  </button>
                                </div>
                                <pre className="code-box">{log.sanitized_prompt}</pre>
                              </div>

                              {log.final_response ? (
                                <div className="payload-block">
                                  <div className="block-header">
                                    <span>Model Response Output</span>
                                    <button
                                      className="mini-copy-btn"
                                      onClick={() => copyToClipboard(log.final_response || "", `resp-${log.log_id}`)}
                                    >
                                      {respCopied ? "✓ Copied!" : "📋 Copy Response"}
                                    </button>
                                  </div>
                                  <pre className="code-box response-box">{log.final_response}</pre>
                                </div>
                              ) : null}
                            </div>
                          </details>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
      {showConfirmModal && (
        <ActionConfirmationModal
          isOpen={showConfirmModal}
          onClose={() => setShowConfirmModal(false)}
          proposedItems={pendingConfirmItems}
          onConfirm={handleConfirmBatchActions}
        />
      )}
    </div>
  );
}
