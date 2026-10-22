import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

let deferredInstallPrompt: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notifyListeners() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e as BeforeInstallPromptEvent;
    notifyListeners();
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    notifyListeners();
  });
}

export function isRunningStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const isStandaloneMedia =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(display-mode: standalone)").matches;
  const isIosStandalone = Boolean((window.navigator as any)?.standalone);
  return isStandaloneMedia || isIosStandalone;
}

export function isIosDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent || "");
}

export function usePwaInstall() {
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(deferredInstallPrompt);
  const [standalone, setStandalone] = useState<boolean>(() => isRunningStandalone());
  const [showGuide, setShowGuide] = useState(false);

  useEffect(() => {
    const update = () => {
      setPromptEvent(deferredInstallPrompt);
      setStandalone(isRunningStandalone());
    };
    listeners.add(update);
    return () => {
      listeners.delete(update);
    };
  }, []);

  const triggerInstall = async () => {
    if (deferredInstallPrompt) {
      await deferredInstallPrompt.prompt();
      const choice = await deferredInstallPrompt.userChoice;
      if (choice.outcome === "accepted") {
        deferredInstallPrompt = null;
        notifyListeners();
      }
    } else {
      setShowGuide(true);
    }
  };

  return {
    canNativePrompt: Boolean(promptEvent),
    isStandalone: standalone,
    isIos: isIosDevice(),
    showGuide,
    setShowGuide,
    triggerInstall,
  };
}

export function InstallAppModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const isIos = isIosDevice();
  if (!isOpen) return null;

  return (
    <div className="account-sheet-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Add CineQueue to Home Screen">
      <div className="account-sheet-container" onClick={(e) => e.stopPropagation()}>
        <div className="account-sheet-drag-handle" aria-hidden="true" />
        <div className="account-sheet-header">
          <img
            src="/icon-192.png"
            alt="CineQueue App Icon"
            style={{ width: 52, height: 52, borderRadius: 12, boxShadow: "0 4px 14px rgba(0,0,0,0.4)" }}
          />
          <div className="account-user-details">
            <h3>Install CineQueue App</h3>
            <p className="account-user-email">Launch full-screen from your Home Screen with offline local storage</p>
          </div>
          <button type="button" className="account-sheet-close-btn" onClick={onClose} aria-label="Close install guide">
            ✕
          </button>
        </div>

        <div className="account-section" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {isIos ? (
            <>
              <div className="install-step-row">
                <span className="install-step-num">1</span>
                <span>Tap the <strong>Share</strong> button <span aria-hidden="true">⎋</span> at the bottom of Safari.</span>
              </div>
              <div className="install-step-row">
                <span className="install-step-num">2</span>
                <span>Scroll down and tap <strong>Add to Home Screen</strong> <span aria-hidden="true">➕</span>.</span>
              </div>
              <div className="install-step-row">
                <span className="install-step-num">3</span>
                <span>Tap <strong>Add</strong> in the top-right corner to place the CineQueue icon on your Home Screen.</span>
              </div>
            </>
          ) : (
            <>
              <div className="install-step-row">
                <span className="install-step-num">1</span>
                <span>Open your browser menu (<strong>⋮</strong> in Chrome or <strong>⋯</strong> in Edge/Safari).</span>
              </div>
              <div className="install-step-row">
                <span className="install-step-num">2</span>
                <span>Select <strong>Install app</strong> or <strong>Add to Home screen</strong>.</span>
              </div>
              <div className="install-step-row">
                <span className="install-step-num">3</span>
                <span>Launch CineQueue directly from your Home Screen like a native app!</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
