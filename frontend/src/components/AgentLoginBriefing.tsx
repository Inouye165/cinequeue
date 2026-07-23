import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AgentBriefing } from "../types";

interface AgentLoginBriefingProps {
  onOpenChat: () => void;
}

export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/\[System Note:[^\]]*\]/gi, "")
    .replace(/[*_~`#]+/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function AgentLoginBriefing({ onOpenChat }: AgentLoginBriefingProps) {
  const [briefing, setBriefing] = useState<AgentBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const loadBriefing = async (forceNewSession: boolean = false) => {
    setLoading(true);
    try {
      let sessionId = forceNewSession ? null : sessionStorage.getItem("cinequeue_briefing_session_id");
      if (!sessionId || forceNewSession) {
        sessionId = "sess_" + Date.now() + "_" + Math.random().toString(36).substring(2, 9);
        sessionStorage.setItem("cinequeue_briefing_session_id", sessionId);
      }

      const data = await api.agentBriefing(sessionId);
      if (data && data.enabled && data.briefing) {
        setBriefing(data);

        // Short delay before startup greeting is spoken
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
    // Generate fresh session on initial page load
    void loadBriefing(true);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  if (loading || !briefing || !briefing.briefing) {
    return null;
  }

  const presetLabels: Record<string, string> = {
    cinephile: "🎬 Cinephile Critic Briefing",
    noir: "🕵️ Film Noir Detective Briefing",
    scifi: "🤖 Sci-Fi AI Telemetry",
    sarcastic: "😼 Sarcastic Buddy Update",
    custom: "✍️ Agent Briefing",
  };

  const label = presetLabels[briefing.personality_preset || "cinephile"] || "🤖 Agent Briefing";

  return (
    <section className="agent-briefing-card" aria-label="AI Agent Greeting Briefing">
      <div className="briefing-left">
        <div className="briefing-header">
          <span className="briefing-tag">{label}</span>
          {briefing.updates_count ? (
            <span className="updates-count-badge">
              {briefing.updates_count} update{briefing.updates_count > 1 ? "s" : ""}
            </span>
          ) : null}
          {isSpeaking ? (
            <span className="speaking-badge" title="Speaking out loud">
              🔊 Playing Audio…
            </span>
          ) : null}
        </div>
        <p className="briefing-text">{briefing.briefing}</p>
      </div>

      <div className="briefing-actions">
        <button
          className={`listen-again-btn ${isSpeaking ? "active" : ""}`}
          onClick={() => {
            if (briefing.briefing) {
              speakText(briefing.briefing);
            }
          }}
          title="Listen to the startup briefing again"
        >
          {isSpeaking ? "🔊 Speaking..." : "🔊 Listen"}
        </button>
        <button className="chat-briefing-btn" onClick={onOpenChat}>
          💬 Chat with AI
        </button>
      </div>
    </section>

  );
}
