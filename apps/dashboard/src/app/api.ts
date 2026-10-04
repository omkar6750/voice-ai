import { createContext, useContext } from "react";

export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;
export const ApiContext = createContext<Api | null>(null);
export const SupportSessionContext = createContext<string | null>(null);

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly diagnostic?: {
      diagnostic_id?: string;
      stage?: string;
      timestamp?: string;
    },
  ) {
    super(message);
    this.name = "ApiError";
  }
}
const apiOrigin = (import.meta.env.VITE_API_ORIGIN ?? "").replace(/\/$/, "");

export function healthUrl(): string {
  const origin =
    apiOrigin ||
    (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);
  return new URL("/health", origin).toString();
}

export function runtimeHealthUrl(): string | null {
  const origin =
    import.meta.env.VITE_RUNTIME_ORIGIN ||
    (import.meta.env.DEV ? "http://127.0.0.1:8001" : "");
  return origin ? new URL("/health", origin).toString() : null;
}

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
    console.debug(
      `[voice-api] ${init.method ?? "GET"} ${path} ${response.status} ${(performance.now() - startedAt).toFixed(0)}ms`,
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message =
      typeof detail === "object" &&
      detail !== null &&
      !Array.isArray(detail) &&
      typeof detail.message === "string"
        ? detail.message
        : typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((item: { msg?: string; loc?: (string | number)[] }) => {
                  const field = (item.loc ?? [])
                    .filter((part, index) => !(index === 0 && part === "body"))
                    .reduce<string>(
                      (path, part) =>
                        typeof part === "number"
                          ? `${path}[${part}]`
                          : path
                            ? `${path}.${part}`
                            : part,
                      "",
                    );
                  return `${field ? `${field}: ` : ""}${item.msg ?? "Invalid value"}`;
                })
                .join("; ")
            : `Request failed (${response.status})`;
    throw new ApiError(
      response.status,
      message,
      typeof detail === "object" && !Array.isArray(detail)
        ? detail
        : payload?.diagnostic_id
          ? {
              diagnostic_id: payload.diagnostic_id,
              stage: payload.stage,
              timestamp: payload.timestamp,
            }
          : undefined,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export async function requestBlob(
  token: string,
  path: string,
  supportSession?: string | null,
): Promise<Blob> {
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  if (supportSession) headers.set("X-Platform-Support-Session", supportSession);
  const response = await fetch(apiUrl(path), {
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status})`,
    );
  }
  return response.blob();
}
