import { useEffect, useState } from "react";
import { api } from "../api";
import type { AgentBriefing } from "../types";

interface AgentLoginBriefingProps {
  onOpenChat: () => void;
}

export function AgentLoginBriefing({ onOpenChat }: AgentLoginBriefingProps) {
  const [briefing, setBriefing] = useState<AgentBriefing | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const fetchBriefing = async () => {
      try {
        const data = await api.agentBriefing();
        if (active && data && data.enabled && data.briefing) {
          setBriefing(data);
        }
      } catch (err) {
        console.error("Failed to load agent briefing:", err);
      } finally {
        if (active) setLoading(false);
      }
    };

    void fetchBriefing();

    return () => {
      active = false;
    };
  }, []);

  if (loading || !briefing || dismissed || !briefing.briefing) {
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
    <div className="agent-briefing-banner">
      <div className="briefing-left">
        <div className="briefing-header">
          <span className="briefing-tag">{label}</span>
          {briefing.updates_count ? (
            <span className="updates-count-badge">{briefing.updates_count} update{briefing.updates_count > 1 ? "s" : ""}</span>
          ) : null}
        </div>
        <p className="briefing-text">{briefing.briefing}</p>
      </div>

      <div className="briefing-actions">
        <button className="chat-briefing-btn" onClick={onOpenChat}>
          💬 Chat with AI
        </button>
        <button className="dismiss-briefing-btn" onClick={() => setDismissed(true)} title="Dismiss">
          &times;
        </button>
      </div>
    </div>
  );
}
