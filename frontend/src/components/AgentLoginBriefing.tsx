import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { cancelSpeech, speakSpeechText } from "../utils/speech";
import type { AgentBriefing, AgentBriefingUpdate } from "../types";

export { cleanTextForSpeech } from "../utils/speech";

interface AgentLoginBriefingProps {
  ownerId?: string;
  onOpenChat: () => void;
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

export function AgentLoginBriefing({ ownerId, onOpenChat }: AgentLoginBriefingProps) {
  const storageScope = ownerId || "local";
  const [briefing, setBriefing] = useState<AgentBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [showUpdatesModal, setShowUpdatesModal] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDismissed] = useState(() => {
    return sessionStorage.getItem(`cinequeue_briefing_dismissed:${storageScope}`) === "true";
  });

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasRequestedBriefingRef = useRef(false);
  const briefingAbortRef = useRef<AbortController | null>(null);

  const speakText = (text: string) => {
    speakSpeechText(text, {
      onStart: () => setIsSpeaking(true),
      onEnd: () => setIsSpeaking(false),
    });
  };

  const loadBriefing = async (forceRefresh: boolean = false, signal?: AbortSignal) => {
    if (loading && forceRefresh) return;
    briefingAbortRef.current?.abort();
    const controller = new AbortController();
    briefingAbortRef.current = controller;
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    setLoading(true);
    try {
      const sessionKey = `cinequeue_briefing_session_id:${storageScope}`;
      let sessionId = sessionStorage.getItem(sessionKey);
      if (!sessionId) {
        sessionId = "sess_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
        sessionStorage.setItem(sessionKey, sessionId);
      }

      const data = await api.agentBriefing(sessionId, forceRefresh, { signal: controller.signal });
      if (!controller.signal.aborted && data && data.enabled && data.briefing) {
        setBriefing(data);
        if (data.auto_speak_briefing === true && !isDismissed) {
          speakText(data.briefing);
        }
      }
    } catch (err) {
      if (controller.signal.aborted || (err instanceof Error && err.name === "AbortError")) return;
      console.error("Failed to load agent briefing:", err);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    if (!hasRequestedBriefingRef.current) {
      hasRequestedBriefingRef.current = true;
      void loadBriefing(false, controller.signal);
    }

    return () => {
      controller.abort();
      briefingAbortRef.current?.abort();
      hasRequestedBriefingRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      cancelSpeech();
    };
  }, []);

  const count = briefing?.updates_count ?? briefing?.updates?.length ?? 0;
  if (loading || !briefing || !briefing.briefing || count === 0 || isDismissed) {
    return null;
  }

  const cleanedText = cleanBriefingForDisplay(briefing.briefing);
  const { headline, supportingText } = formatSummaryLines(cleanedText, briefing.updates, briefing.updates_count);

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
              if (isSpeaking) {
                cancelSpeech();
                setIsSpeaking(false);
              } else if (briefing.briefing) {
                speakText(briefing.briefing);
              }
            }}
            aria-label={isSpeaking ? "Stop audio" : "Listen out loud"}
            title={isSpeaking ? "Stop audio" : "Listen out loud"}
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
