import { createContext, useContext } from "react";

export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;
export const ApiContext = createContext<Api | null>(null);
export const SupportSessionContext = createContext<string | null>(null);
const apiOrigin = (import.meta.env.VITE_API_ORIGIN ?? "").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${apiOrigin}/api/v1${path}`;
}

export function websocketUrl(path: string): string {
  const url = new URL(apiUrl(path), window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("API unavailable");
  return api;
}

export function useSupportSession(): string | null {
  return useContext(SupportSessionContext);
}

export async function request<T>(
  sessionToken: string,
  path: string,
  init: RequestInit = {},
  supportSession?: string | null,
): Promise<T> {
  const startedAt = performance.now();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${sessionToken}`);
  if (supportSession) headers.set("X-Platform-Support-Session", supportSession);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(apiUrl(path), { ...init, headers });
  if (import.meta.env.VITE_DEBUG_PERF === "true") {
    console.debug(`[voice-api] ${init.method ?? "GET"} ${path} ${response.status} ${(performance.now() - startedAt).toFixed(0)}ms`);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item: { msg?: string }) => item.msg ?? "Invalid value")
              .join("; ")
          : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export async function requestBlob(token: string, path: string, supportSession?: string | null): Promise<Blob> {
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  if (supportSession) headers.set("X-Platform-Support-Session", supportSession);
  const response = await fetch(apiUrl(path), {
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status})`,
    );
  }
  return response.blob();
}
