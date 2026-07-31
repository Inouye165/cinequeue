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
): { headline: string; supportingText: string } {
  const count = updatesCount ?? updates?.length ?? 0;

  if (updates && updates.length > 0) {
    const first = updates[0];
    let msg = first.message || first.summary || first.title || "";
    msg = msg
      .replace(/\[System Note:[^\]]*\]/gi, "")
      .replace(/[*_~`#]+/g, "")
      .replace(/•?\s*MEMORY RECALL:\s*/gi, "")
      .replace(/•?\s*Random movie fact:[^\n]*/gi, "")
      .replace(/^You asked about (.+?) on \d{4}-\d{2}-\d{2}\.?$/i, "$1 is now available.")
      .replace(/\s+/g, " ")
      .trim();

    const headline = count === 1 ? "1 new update since last visit" : `${count} new updates available`;
    return { headline, supportingText: msg };
  }

  const cleaned = cleanBriefingForDisplay(briefingText);
  if (!cleaned) {
    return {
      headline: "You’re all caught up",
      supportingText: "No new releases or episodes have appeared since your last visit.",
    };
  }

  const sentences = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const headline = sentences[0] || "You’re all caught up";
  const supportingText =
    sentences.length > 1 ? sentences[1] : "No new releases or episodes have appeared since your last visit.";

  return { headline, supportingText };
}

export function AgentLoginBriefing({ onOpenChat }: AgentLoginBriefingProps) {
  const [briefing, setBriefing] = useState<AgentBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [showUpdatesModal, setShowUpdatesModal] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDismissed] = useState(() => {
    return sessionStorage.getItem("cinequeue_briefing_dismissed") === "true";
  });

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasRequestedBriefingRef = useRef(false);

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

  if (loading || !briefing || !briefing.briefing || isDismissed) {
    return null;
  }

  const cleanedText = cleanBriefingForDisplay(briefing.briefing);
  const { headline, supportingText } = formatSummaryLines(cleanedText, briefing.updates, briefing.updates_count);
  const count = briefing.updates_count ?? briefing.updates?.length ?? 0;

  return (
    <>
      <section
        className={`concise-daily-update ${isExpanded ? "expanded" : "collapsed"}`}
        aria-label="Personalized Daily Update"
      >
        {/* Eyebrow */}
        <div className="update-eyebrow-row">
          <span className="update-eyebrow">TODAY</span>
          {isSpeaking && <span className="audio-active-badge">🔊 Audio Active</span>}
        </div>

        {/* Headline & Supporting Text */}
        <div className="update-content">
          <h2 className="update-headline">{headline}</h2>
          <p className="update-supporting-text">{supportingText}</p>
        </div>

        {/* Progressive Disclosure Content */}
        {isExpanded && (
          <div id="briefing-expanded-content" className="update-expanded-details">
            {cleanedText && <p className="full-briefing-text">{cleanedText}</p>}

            {briefing.updates && briefing.updates.length > 0 && (
              <div className="update-items-list">
                {briefing.updates.map((item, idx) => (
                  <div key={idx} className="update-item-card">
                    <div className="item-card-top">
                      <span className="item-title">{item.title}</span>
                      <span className="item-type">{item.type || "update"}</span>
                    </div>
                    <p className="item-msg">{item.message || item.summary}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Action Row */}
        <div className="update-action-row">
          {count > 0 ? (
            <button
              type="button"
              className="pill-button primary update-main-btn"
              onClick={() => setShowUpdatesModal(true)}
            >
              🔍 View updates ({count})
            </button>
          ) : (
            <button
              type="button"
              className="pill-button primary update-main-btn"
              onClick={onOpenChat}
            >
              💬 Ask CineQueue
            </button>
          )}

          <button
            type="button"
            className={`audio-toggle-btn ${isSpeaking ? "speaking" : ""}`}
            onClick={() => {
              if (briefing.briefing) {
                speakText(briefing.briefing);
              }
            }}
            aria-label={isSpeaking ? "Stop audio" : "Listen out loud"}
            title="Listen out loud"
          >
            {isSpeaking ? "⏹️" : "🔊"}
          </button>

          <button
            type="button"
            className="chevron-expand-btn"
            onClick={() => setIsExpanded((prev) => !prev)}
            aria-expanded={isExpanded}
            aria-controls="briefing-expanded-content"
            aria-label={isExpanded ? "Collapse details" : "Expand details"}
          >
            <span className={`chevron-icon ${isExpanded ? "open" : ""}`} aria-hidden="true">
              ▼
            </span>
          </button>
        </div>
      </section>

      {/* Detailed Updates Modal */}
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
              <h3 id="updates-modal-title">🔔 Recent Queue & Feed Updates</h3>
              <button
                type="button"
                className="updates-modal-close-btn"
                onClick={() => setShowUpdatesModal(false)}
                aria-label="Close updates"
              >
                ✕
              </button>
            </div>
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
                  <p>No detailed log available.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
