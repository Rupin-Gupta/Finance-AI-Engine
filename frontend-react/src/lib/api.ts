/**
 * Typed client for the FastAPI /v1/* surface. The UI talks ONLY to this API
 * (no direct DB) — mirrors the existing separation. Base URL + API key are read
 * from Settings (localStorage), defaulting to same-origin (Vite proxy in dev).
 */
const BASE_KEY = "fae.apiBase";
const KEY_KEY = "fae.apiKey";

// Resolution order: Settings (localStorage) → build-time env (.env.local) → empty.
// Keeps the key out of committed source while letting local dev "just work".
export function getApiBase(): string {
  return localStorage.getItem(BASE_KEY) ?? (import.meta.env.VITE_API_BASE as string) ?? "";
}
export function getApiKey(): string {
  return localStorage.getItem(KEY_KEY) ?? (import.meta.env.VITE_API_KEY as string) ?? "";
}
export function hasApiKey(): boolean {
  return getApiKey().trim().length > 0;
}
export function setApiConfig(base: string, key: string) {
  localStorage.setItem(BASE_KEY, base.trim());
  localStorage.setItem(KEY_KEY, key.trim());
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(getApiBase() + path, {
    method,
    headers: {
      "X-API-Key": getApiKey(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  qs: (params: Record<string, string | number | boolean | undefined>) => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined) u.set(k, String(v));
    const s = u.toString();
    return s ? `?${s}` : "";
  },
};
