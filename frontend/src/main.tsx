import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import {
  clearLegacyTmdbImageCache,
  requestServiceWorkerUpdate,
} from "./utils/pwaCacheMigration";

// Render the local-first app shell immediately without waiting on async cache or SW tasks
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Run legacy cache cleanup and service-worker update check asynchronously in the background
queueMicrotask(() => {
  clearLegacyTmdbImageCache().catch((err) => {
    console.warn("[main] Background legacy cache cleanup failed:", err);
  });
  requestServiceWorkerUpdate().catch((err) => {
    console.warn("[main] Post-render service-worker update failed:", err);
  });
});
