import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { AgentSettings, ChatMessage, PersonalityPreset } from "../types";

interface AgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onWatchlistUpdated?: () => void;
  initialTab?: "chat" | "settings";
}

const PRESETS: { id: PersonalityPreset; name: string; icon: string; desc: string }[] = [
  { id: "cinephile", name: "Cinephile Critic", icon: "🎬", desc: "Passionate, knowledgeable movie & TV enthusiast with witty insights." },
  { id: "noir", name: "Film Noir Detective", icon: "🕵️", desc: "Cynical 1940s detective viewing your queue through rain-slicked streets." },
  { id: "scifi", name: "Sci-Fi AI", icon: "🤖", desc: "Crisp, precise futuristic AI unit managing media telemetry archives." },
  { id: "sarcastic", name: "Sarcastic Buddy", icon: "😼", desc: "Hilarious, sarcastic friend who gives great advice with playful jabs." },
  { id: "custom", name: "Custom Persona", icon: "✍️", desc: "Define your own unique AI system instructions and tone." },
];

const SUGGESTIONS = [
  "What updates do I have on my monitored shows?",
  "I'm waiting for Severance season 2",
  "Notify me when Oppenheimer drops under $4 to rent",
  "Recommend a great sci-fi movie for tonight",
];

export function AgentModal({ isOpen, onClose, onWatchlistUpdated, initialTab = "chat" }: AgentModalProps) {
  const [activeTab, setActiveTab] = useState<"chat" | "settings">(initialTab);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loadingChat, setLoadingChat] = useState(false);
  const [sending, setSending] = useState(false);

  const [settings, setSettings] = useState<AgentSettings>({
    personality_preset: "cinephile",
    custom_prompt: "",
    location: "",
    notify_on_login: true,
    auto_add_mentioned: true,
    track_price_drops: true,
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSavedToast, setSettingsSavedToast] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      void loadChatHistory();
      void loadSettings();
    }
  }, [isOpen, initialTab]);

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
        </div>

        {/* Content Body */}
        <div className="agent-modal-body">
          {activeTab === "chat" ? (
            <div className="agent-chat-view">
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
                            <div className="chat-actions-list">
                              {msg.actions.map((act, aIdx) => (
                                <div key={aIdx} className="chat-action-tag">
                                  {act.action === "add_monitoring" || act.action === "update_monitoring"
                                    ? `🎯 Added "${act.title}" to Monitoring`
                                    : `💲 Rental Target set to $${act.target_rental_price?.toFixed(2)}`}
                                </div>
                              ))}
                            </div>
                          ) : null}
                          <div className="chat-bubble-footer">
                            {msg.role === "assistant" ? (
                              <button
                                className="speak-bubble-btn"
                                onClick={() => {
                                  if (!("speechSynthesis" in window)) return;
                                  window.speechSynthesis.cancel();
                                  const clean = msg.content
                                    .replace(/\[System Note:[^\]]*\]/gi, "")
                                    .replace(/[*_~`#]+/g, "")
                                    .replace(/https?:\/\/\S+/g, "")
                                    .replace(/\s+/g, " ")
                                    .trim();
                                  if (clean) {
                                    window.speechSynthesis.speak(new SpeechSynthesisUtterance(clean));
                                  }
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
          ) : (
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
              </div>

              <div className="settings-actions">
                {settingsSavedToast ? <span className="saved-toast">✓ Settings saved!</span> : <span />}
                <button className="save-settings-btn" onClick={() => void handleSaveSettings()} disabled={savingSettings}>
                  {savingSettings ? "Saving…" : "Save Agent Settings"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
