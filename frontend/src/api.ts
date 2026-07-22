import type { MediaDetails, MediaItem, WatchlistItem } from "./types";
import { getApps } from "firebase/app";
import { getAuth } from "firebase/auth";
import {
  getActiveTrace,
  recordEvent,
  detectDuplicateMeRequest,
  detectPrematureMeRequest,
} from "./utils/authPerformanceMonitor";

export interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  messagingSenderId?: string;
}

export interface CsrfResponse {
  csrf_token: string;
}

export interface UserMe {
  uid: string;
  email: string;
  display_name?: string;
  photo_url?: string;
}

function getCookie(name: string): string | null {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

let adminMeRequestCount = 0;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const reqInit = { ...init };
  reqInit.credentials = "include"; // Ensure cookies are sent
  
  const method = reqInit.method?.toUpperCase() || "GET";
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    const csrfToken = getCookie("cinequeue_csrf");
    if (csrfToken) {
      const headers = { ...(reqInit.headers as Record<string, string>) };
      headers["X-CSRF-Token"] = csrfToken;
      reqInit.headers = headers;
    }
  }

  // Append X-Auth-Trace-Id if trace is active
  const activeTrace = getActiveTrace();
  if (activeTrace) {
    const headers = { ...(reqInit.headers as Record<string, string>) };
    headers["X-Auth-Trace-Id"] = activeTrace.traceId;
    reqInit.headers = headers;
  }

  const isAdminMe = path === "/api/admin/me";
  let requestStartTime = 0;
  let headersArrivedTime = 0;
  let jsonParsedTime = 0;

  if (isAdminMe) {
    adminMeRequestCount++;
    detectDuplicateMeRequest();
    
    let firebaseUserExists = false;
    let authInitializationComplete = false;
    try {
      if (getApps().length > 0) {
        const auth = getAuth();
        firebaseUserExists = !!auth.currentUser;
        authInitializationComplete = true;
      }
    } catch (e) {}

    detectPrematureMeRequest({
      firebaseUserExists,
      tokenExists: firebaseUserExists,
      authInitializationComplete,
      requestSequence: adminMeRequestCount,
    });

    recordEvent("admin_me_request_started", "start", {
      sequenceNumber: adminMeRequestCount,
      authAttached: !!reqInit.headers && ("Authorization" in reqInit.headers || "X-CSRF-Token" in reqInit.headers),
    });
    requestStartTime = performance.now();
  }

  let response: Response;
  try {
    response = await fetch(path, reqInit);
    if (isAdminMe) {
      headersArrivedTime = performance.now();
    }
  } catch (err: any) {
    if (isAdminMe) {
      recordEvent("admin_me_request_failed", "failure", {
        error: err.message,
        aborted: err.name === "AbortError",
        durationMs: performance.now() - requestStartTime,
      });
    }
    throw err;
  }

  if (isAdminMe) {
    // Extract backend perf timings from headers
    const tvMs = response.headers.get("X-Auth-Perf-Token-Verification-Ms");
    const alMs = response.headers.get("X-Auth-Perf-Admin-Lookup-Ms");
    if (activeTrace) {
      activeTrace.backendTimings = {
        tokenVerificationMs: tvMs ? parseFloat(tvMs) : undefined,
        adminLookupMs: alMs ? parseFloat(alMs) : undefined,
        totalBackendMs: (tvMs ? parseFloat(tvMs) : 0) + (alMs ? parseFloat(alMs) : 0),
      };
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("cinequeue-unauthorized"));
    }
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    if (isAdminMe) {
      recordEvent("admin_me_request_failed", "failure", {
        status: response.status,
        detail: error.detail,
        durationMs: performance.now() - requestStartTime,
      });
    }
    const detailMsg =
      typeof error.detail === "string"
        ? error.detail
        : Array.isArray(error.detail)
        ? error.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
        : error.detail
        ? JSON.stringify(error.detail)
        : "Request failed";
    throw new Error(detailMsg);
  }


  const data = await response.json();
  if (isAdminMe) {
    jsonParsedTime = performance.now();
    recordEvent("admin_me_response_received", "success", {
      status: response.status,
      fetchDurationMs: headersArrivedTime - requestStartTime,
      jsonParseDurationMs: jsonParsedTime - headersArrivedTime,
      totalDurationMs: jsonParsedTime - requestStartTime,
    });
  }
  return data;
}

export const api = {
  // Auth endpoints
  firebaseConfig: () => request<FirebaseConfig>("/api/auth/config"),
  csrf: () => request<CsrfResponse>("/api/auth/csrf"),
  createSession: (idToken: string, csrfToken: string) =>
    request<{ status: string }>("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken, csrf_token: csrfToken }),
    }),
  me: () => request<UserMe>("/api/auth/me"),
  logout: (csrfToken: string) =>
    request<{ status: string }>("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token: csrfToken }),
    }),

  // Admin endpoints
  adminLogin: (username: string, password: string, csrfToken: string) =>
    request<{ status: string }>("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, csrf_token: csrfToken }),
    }),
  adminLogout: (csrfToken: string) =>
    request<{ status: string }>("/api/admin/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token: csrfToken }),
    }),
  adminMe: (token: string) => {
    if (!token) {
      throw new Error("[AuthPerformance] /api/admin/me called without a token");
    }
    return request<{ username: string }>("/api/admin/me", {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
  },
  adminRequests: (token?: string, signal?: AbortSignal) => {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return request<{ approvals: Array<{ email: string; status: string; requested_at: string; decided_at?: string; decided_by?: string }> }>(
      "/api/admin/requests",
      { headers, signal }
    );
  },
  adminApprove: (email: string, csrfToken: string, token?: string) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return request<{ status: string }>("/api/admin/approve", {
      method: "POST",
      headers,
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    });
  },
  adminDeny: (email: string, csrfToken: string, token?: string) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return request<{ status: string }>("/api/admin/deny", {
      method: "POST",
      headers,
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    });
  },
  adminInvite: (email: string, csrfToken: string, token?: string) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return request<{ status: string }>("/api/admin/invite", {
      method: "POST",
      headers,
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    });
  },
  adminLoginLogs: (token?: string, signal?: AbortSignal) => {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return request<{ logs: Array<{ id: string | number; email: string; timestamp: string; status: string; reason: string; ip_address?: string; user_agent?: string }> }>(
      "/api/admin/login-logs",
      { headers, signal }
    );
  },

  // Watchlist & movies endpoints
  search: (q: string) => request<MediaItem[]>(`/api/search?q=${encodeURIComponent(q)}`),
  upcoming: () => request<MediaItem[]>("/api/upcoming"),
  nowPlaying: () => request<MediaItem[]>("/api/now-playing"),
  trending: () => request<MediaItem[]>("/api/trending"),
  onAir: () => request<MediaItem[]>("/api/on-air"),
  details: (mediaType: string, id: number) =>
    request<MediaDetails>(`/api/${mediaType}/${id}`),
  watchlist: () => request<WatchlistItem[]>("/api/watchlist"),
  addToWatchlist: (item: Partial<WatchlistItem>) =>
    request<WatchlistItem>("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    }),
  updateWatchlistItem: (
    mediaType: string,
    tmdbId: number,
    isOwned?: boolean,
    ownedFormat?: string | null,
    status?: string,
    watchFreeStreaming?: boolean,
    watchOnSaleBuy?: boolean
  ) =>
    request<{
      status: string;
      is_owned: boolean;
      owned_format: string | null;
      status_value?: string;
      watch_free_streaming?: boolean;
      watch_on_sale_buy?: boolean;
    }>(`/api/watchlist/${mediaType}/${tmdbId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        is_owned: isOwned,
        owned_format: ownedFormat,
        status,
        watch_free_streaming: watchFreeStreaming,
        watch_on_sale_buy: watchOnSaleBuy,
      }),
    }),
  removeFromWatchlist: (mediaType: string, tmdbId: number) =>
    request<{ status: string }>(`/api/watchlist/${mediaType}/${tmdbId}`, {
      method: "DELETE",
    }),

  // AI Agent Endpoints
  agentBriefing: () => request<import("./types").AgentBriefing>("/api/agent/briefing"),
  agentSettings: () => request<import("./types").AgentSettings>("/api/agent/settings"),
  saveAgentSettings: (settings: Partial<import("./types").AgentSettings>) =>
    request<import("./types").AgentSettings>("/api/agent/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),
  agentChatHistory: () => request<import("./types").ChatMessage[]>("/api/agent/chat"),
  sendAgentChatMessage: (message: string) =>
    request<{ message: import("./types").ChatMessage; actions_taken: import("./types").ChatAction[] }>("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
  clearAgentChatHistory: () =>
    request<{ status: string }>("/api/agent/chat", {
      method: "DELETE",
    }),
};

