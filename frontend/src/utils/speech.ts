/** Shared speech synthesis helpers for AI agent briefings and chat responses. */

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

export function cancelSpeech(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

export function speakSpeechText(
  text: string,
  callbacks?: { onStart?: () => void; onEnd?: () => void }
): boolean {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return false;
  }
  window.speechSynthesis.cancel();
  const clean = cleanTextForSpeech(text);
  if (!clean) return false;

  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.onstart = () => callbacks?.onStart?.();
  utterance.onend = () => callbacks?.onEnd?.();
  utterance.onerror = () => callbacks?.onEnd?.();
  window.speechSynthesis.speak(utterance);
  return true;
}
