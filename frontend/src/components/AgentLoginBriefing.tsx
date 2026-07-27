import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AgentBriefing, AgentBriefingUpdate } from "../types";

interface AgentLoginBriefingProps {
  onOpenChat: () => void;
}

export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/\[System Note:[^\]]*\]/gi, "")
    .replace(/[*_~`#]+/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\bMEMORY RECALL:\s*/gi, "")
    .replace(/•\s*Random movie fact:[^\n]*/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function cleanBriefingForDisplay(text: string): string {
  if (!text) return "";
  return text
    .replace(/\[System Note:[^\]]*\]/gi, "")
    .replace(/[*_~`#]+/g, "")
    .replace(/•?\s*MEMORY RECALL:\s*/gi, "")
    .replace(/•?\s*Random movie fact:[^\n]*\n?/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function formatSummaryLines(
  briefingText: string,
  updates?: AgentBriefingUpdate[],
  updatesCount?: number
): { line1: string; line2?: string } {
  if (updates && updates.length > 0) {
    const first = updates[0];
    let line1 = first.message || first.summary || first.title || "";
    line1 = line1
      .replace(/\[System Note:[^\]]*\]/gi, "")
      .replace(/[*_~`#]+/g, "")
      .replace(/•?\s*MEMORY RECALL:\s*/gi, "")
      .replace(/•?\s*Random movie fact:[^\n]*/gi, "")
      .replace(/^You asked about (.+?) on \d{4}-\d{2}-\d{2}\.?$/i, "$1 is now available.")
      .replace(/\s+/g, " ")
      .trim();

    if (!line1) {
      line1 = first.title ? `${first.title} is available.` : "New update available.";
    }

    const totalCount = updatesCount ?? updates.length;
    let line2: string | undefined;
    if (totalCount > 1) {
      const remaining = totalCount - 1;
      line2 =
        remaining === 1
          ? "There is 1 additional monitored-title update."
          : `There are ${remaining} additional monitored-title updates.`;
    }

    return { line1, line2 };
  }

  const cleaned = cleanBriefingForDisplay(briefingText);
  if (!cleaned) {
    return { line1: "Your queue and monitored titles are up to date." };
  }

  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const line1 = sentences[0] || "Your queue and monitored titles are up to date.";
  const line2 = sentences.length > 1 && sentences[1].length < 90 ? sentences[1] : undefined;

  return { line1, line2 };
}

export function AgentLoginBriefing({ onOpenChat }: AgentLoginBriefingProps) {
  const [briefing, setBriefing] = useState<AgentBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [showUpdatesModal, setShowUpdatesModal] = useState(false);
  const [hasAcknowledgedUpdates, setHasAcknowledgedUpdates] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isDismissed, setIsDismissed] = useState(() => {
    return sessionStorage.getItem("cinequeue_briefing_dismissed") === "true";
  });

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasRequestedBriefingRef = useRef(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);

  const speakText = (text: string) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();

    const clean = cleanTextForSpeech(text);
    if (!clean) return;

    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const loadBriefing = async (forceRefresh: boolean = false) => {
    if (loading && forceRefresh) return;
    setLoading(true);
    try {
      let sessionId = sessionStorage.getItem("cinequeue_briefing_session_id");
      if (!sessionId) {
        sessionId = "sess_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
        sessionStorage.setItem("cinequeue_briefing_session_id", sessionId);
      }

      const data = await api.agentBriefing(sessionId, forceRefresh);
      if (data && data.enabled && data.briefing) {
        setBriefing(data);

        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
          if (data.briefing) {
            speakText(data.briefing);
          }
        }, 1200);
      }
    } catch (err) {
      console.error("Failed to load agent briefing:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!hasRequestedBriefingRef.current) {
      hasRequestedBriefingRef.current = true;
      void loadBriefing(false);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        menuTriggerRef.current &&
        !menuTriggerRef.current.contains(e.target as Node)
      ) {
        setIsMenuOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isMenuOpen) {
        setIsMenuOpen(false);
        menuTriggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen]);

  const handleDismiss = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    sessionStorage.setItem("cinequeue_briefing_dismissed", "true");
    setIsDismissed(true);
  };

  if (loading || !briefing || !briefing.briefing || isDismissed) {
    return null;
  }

  const presetLabels: Record<string, string> = {
    cinephile: "🎬 Cinephile Critic Briefing",
    noir: "🕵️ Film Noir Briefing",
    scifi: "🤖 AI Telemetry Briefing",
    sarcastic: "😼 Buddy Briefing",
    custom: "✍️ Agent Briefing",
  };

  const label = presetLabels[briefing.personality_preset || "cinephile"] || "🤖 Agent Briefing";
  const cleanedText = cleanBriefingForDisplay(briefing.briefing);
  const summary = formatSummaryLines(cleanedText, briefing.updates, briefing.updates_count);
  const count = briefing.updates_count ?? briefing.updates?.length ?? 0;
  const countLabel = count === 1 ? "1 new update" : count > 1 ? `${count} new updates` : "All caught up";

  return (
    <>
      <section
        className={`agent-briefing-card ${isExpanded ? "expanded" : "collapsed"}`}
        aria-label="AI Agent Greeting Briefing"
      >
        <div className="briefing-card-top-bar">
          <div className="briefing-header-left">
            <span className="briefing-tag">{label}</span>
            <span className="briefing-update-count-text">{countLabel}</span>
            {isSpeaking ? (
              <span className="speaking-badge" title="Speaking out loud">
                🔊 Audio Active
              </span>
            ) : null}
          </div>

          <div className="briefing-header-controls">
            <button
              type="button"
              className="briefing-toggle-btn"
              onClick={() => setIsExpanded((prev) => !prev)}
              aria-expanded={isExpanded}
              aria-controls="briefing-details-content"
              aria-label={isExpanded ? "Hide details" : "Show details"}
            >
              {isExpanded ? "Hide details ▲" : "Show details ▼"}
            </button>

            <button
              ref={menuTriggerRef}
              type="button"
              className="briefing-menu-trigger"
              onClick={() => setIsMenuOpen((prev) => !prev)}
              aria-expanded={isMenuOpen}
              aria-haspopup="true"
              aria-label="Briefing options"
            >
              ⋮
            </button>

            {isMenuOpen && (
              <div
                ref={menuRef}
                className="briefing-dropdown-menu"
                role="menu"
                aria-label="Briefing options menu"
              >
                {count > 0 && !hasAcknowledgedUpdates ? (
                  <button
                    type="button"
                    role="menuitem"
                    className="briefing-menu-item"
                    onClick={() => {
                      setHasAcknowledgedUpdates(true);
                      setIsMenuOpen(false);
                      setShowUpdatesModal(true);
                    }}
                  >
                    ✓ Mark updates as read
                  </button>
                ) : null}

                <button
                  type="button"
                  role="menuitem"
                  className="briefing-menu-item"
                  onClick={() => {
                    setIsMenuOpen(false);
                    void loadBriefing(true);
                  }}
                  disabled={loading}
                  aria-label="Refresh briefing"
                >
                  {loading ? "🔄 Refreshing..." : "🔄 Refresh briefing"}
                </button>

                <button
                  type="button"
                  role="menuitem"
                  className="briefing-menu-item dismiss-item"
                  onClick={() => {
                    setIsMenuOpen(false);
                    handleDismiss();
                  }}
                >
                  ✕ Dismiss for today
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="briefing-body">
          <div className="briefing-summary">
            <p className="briefing-summary-line">{summary.line1}</p>
            {summary.line2 && <p className="briefing-summary-line secondary">{summary.line2}</p>}
          </div>

          {isExpanded && (
            <div id="briefing-details-content" className="briefing-details">
              {cleanedText && <p className="briefing-full-text">{cleanedText}</p>}

              {briefing.updates && briefing.updates.length > 0 && (
                <div className="briefing-updates-list">
                  {briefing.updates.map((item, idx) => (
                    <div key={idx} className="briefing-update-item">
                      <div className="briefing-update-item-header">
                        <span className="briefing-update-item-title">{item.title}</span>
                        <span className="briefing-update-item-tag">{item.type || "update"}</span>
                      </div>
                      <p className="briefing-update-item-msg">{item.message || item.summary}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="briefing-actions">
          {count > 0 ? (
            <button
              type="button"
              className="briefing-action-btn primary"
              onClick={() => {
                setHasAcknowledgedUpdates(true);
                setShowUpdatesModal(true);
              }}
            >
              🔍 View updates
            </button>
          ) : (
            <button type="button" className="briefing-action-btn primary" onClick={onOpenChat}>
              💬 Chat with AI
            </button>
          )}

          <button
            type="button"
            className={`briefing-action-btn secondary ${isSpeaking ? "active" : ""}`}
            onClick={() => {
              if (briefing.briefing) {
                speakText(briefing.briefing);
              }
            }}
            title="Listen out loud"
          >
            {isSpeaking ? "🔊 Speaking..." : "🔊 Listen"}
          </button>

          {count > 0 ? (
            <button type="button" className="briefing-action-btn secondary" onClick={onOpenChat}>
              💬 Chat
            </button>
          ) : null}
        </div>
      </section>

      {showUpdatesModal && (
        <div
          className="updates-modal-overlay"
          onClick={() => setShowUpdatesModal(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="updates-modal-title"
        >
          <div className="updates-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="updates-modal-header">
              <h3 id="updates-modal-title">🔔 Updates & Changes Since Last Login</h3>
              <button
                type="button"
                className="updates-modal-close-btn"
                onClick={() => setShowUpdatesModal(false)}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>
            <p className="updates-modal-subtitle">
              The following {count} novel update(s) were found on your queue and news feeds:
            </p>
            <div className="updates-modal-list">
              {briefing.updates && briefing.updates.length > 0 ? (
                briefing.updates.map((item, idx) => (
                  <div key={idx} className="updates-modal-item">
                    <div className="updates-item-top">
                      <span className="updates-item-title">{item.title}</span>
                      <span className="updates-item-tag">{item.type || item.category || "update"}</span>
                    </div>
                    <p className="updates-item-message">{item.message || item.summary}</p>
                  </div>
                ))
              ) : (
                <div className="updates-modal-empty">
                  <p>No detailed item log available for this briefing.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
