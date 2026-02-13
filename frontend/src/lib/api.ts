import Cookies from "js-cookie";

const API_BASE = "/api";
const AUTH_COOKIE = "gb_api_key";

export function getApiKey(): string | undefined {
  return Cookies.get(AUTH_COOKIE);
}

export function setApiKey(key: string): void {
  Cookies.set(AUTH_COOKIE, key, {
    expires: 30,
    sameSite: "strict",
    secure: window.location.protocol === "https:",
  });
}

export function removeApiKey(): void {
  Cookies.remove(AUTH_COOKIE);
}

export function isLiveKey(key: string): boolean {
  return key.startsWith("gb_live_");
}

export function isTestKey(key: string): boolean {
  return key.startsWith("gb_test_");
}

export function isSessionToken(key: string): boolean {
  return key.startsWith("gbs_");
}

export function isValidToken(key: string): boolean {
  return isLiveKey(key) || isTestKey(key) || isSessionToken(key);
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const apiKey = getApiKey();

  if (!apiKey) {
    window.location.href = "/login";
    throw new ApiError(401, "No API key");
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${apiKey}`,
    ...((options.headers as Record<string, string>) || {}),
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    removeApiKey();
    window.location.href = "/login";
    throw new ApiError(401, "Unauthorized");
  }

  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(response.status, body.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint),

  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: "POST",
      body: data ? JSON.stringify(data) : undefined,
    }),

  patch: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: <T>(endpoint: string) =>
    request<T>(endpoint, { method: "DELETE" }),
};
