import { createContext, useContext } from "react";

export type Api = <T>(path: string, init?: RequestInit) => Promise<T>;
export const ApiContext = createContext<Api | null>(null);
export const OperatorTokenContext = createContext("");

export function useOperatorToken() {
  return useContext(OperatorTokenContext);
}

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("API unavailable");
  return api;
}

export async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/v1${path}`, { ...init, headers });
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

export async function requestBlob(token: string, path: string): Promise<Blob> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
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
