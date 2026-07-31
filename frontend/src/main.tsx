import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import {
  clearLegacyTmdbImageCache,
  requestServiceWorkerUpdate,
} from "./utils/pwaCacheMigration";

// Complete legacy cache cleanup before React renders, then request service-worker update asynchronously
clearLegacyTmdbImageCache()
  .catch((err) => {
    console.warn("[main] Pre-render legacy cache cleanup failed:", err);
  })
  .finally(() => {
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    requestServiceWorkerUpdate().catch((err) => {
      console.warn("[main] Post-render service-worker update failed:", err);
    });
  });
