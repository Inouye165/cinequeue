import type { MediaDetails, MediaItem, WatchlistItem } from "./types";

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

  const response = await fetch(path, reqInit);
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("cinequeue-unauthorized"));
    }
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
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
  adminMe: () => request<{ username: string }>("/api/admin/me"),
  adminRequests: () =>
    request<{ approvals: Array<{ email: string; status: string; requested_at: string; decided_at?: string; decided_by?: string }> }>(
      "/api/admin/requests"
    ),
  adminApprove: (email: string, csrfToken: string) =>
    request<{ status: string }>("/api/admin/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    }),
  adminDeny: (email: string, csrfToken: string) =>
    request<{ status: string }>("/api/admin/deny", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    }),
  adminInvite: (email: string, csrfToken: string) =>
    request<{ status: string }>("/api/admin/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, csrf_token: csrfToken }),
    }),
  adminLoginLogs: () =>
    request<{ logs: Array<{ id: string | number; email: string; timestamp: string; status: string; reason: string; ip_address?: string; user_agent?: string }> }>(
      "/api/admin/login-logs"
    ),

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
  updateWatchlistItem: (mediaType: string, tmdbId: number, isOwned?: boolean, ownedFormat?: string | null, status?: string) =>
    request<{ status: string; is_owned: boolean; owned_format: string | null; status_value?: string }>(`/api/watchlist/${mediaType}/${tmdbId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_owned: isOwned, owned_format: ownedFormat, status }),
    }),
  removeFromWatchlist: (mediaType: string, tmdbId: number) =>
    request<{ status: string }>(`/api/watchlist/${mediaType}/${tmdbId}`, {
      method: "DELETE",
    }),
};
