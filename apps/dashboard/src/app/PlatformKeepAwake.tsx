import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Square } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { healthUrl } from "./api";

const STORAGE_KEY = "voice-ai:platform-keep-awake:v1";
const PING_INTERVAL_MS = 10 * 60 * 1000;
const MAX_DURATION_MS = 72 * 60 * 60 * 1000;

type KeepAwakeState = {
  until: number;
  lastAttemptAt: number | null;
  lastResult: "ok" | "error" | null;
  lastStatus: number | null;
};

const disabledState: KeepAwakeState = {
  until: 0,
  lastAttemptAt: null,
  lastResult: null,
  lastStatus: null,
};

let memoryState = disabledState;

function readState(): KeepAwakeState {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (!parsed || typeof parsed !== "object") return memoryState;
    const value = parsed as Partial<KeepAwakeState>;
    if (typeof value.until !== "number" || !Number.isFinite(value.until)) return memoryState;
    memoryState = {
      until: value.until,
      lastAttemptAt: typeof value.lastAttemptAt === "number" ? value.lastAttemptAt : null,
      lastResult: value.lastResult === "ok" || value.lastResult === "error" ? value.lastResult : null,
      lastStatus: typeof value.lastStatus === "number" ? value.lastStatus : null,
    };
    return memoryState;
  } catch {
    return memoryState;
  }
}

function saveState(value: KeepAwakeState): void {
  memoryState = value;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Keep-awake still works in this tab if browser storage is unavailable.
  }
  window.dispatchEvent(new Event("platform-keep-awake-change"));
}

function remainingLabel(until: number, now: number): string {
  const minutes = Math.max(0, Math.ceil((until - now) / 60_000));
  const days = Math.floor(minutes / (24 * 60));
  const hours = Math.floor((minutes % (24 * 60)) / 60);
  const rest = minutes % 60;
  return [days ? `${days}d` : "", hours ? `${hours}h` : "", `${rest}m`].filter(Boolean).join(" ");
}

export function PlatformKeepAwake({ enabled, showControls }: { enabled: boolean; showControls: boolean }) {
  const [state, setState] = useState<KeepAwakeState>(readState);
  const [now, setNow] = useState(Date.now());
  const controllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(() => setState(readState()), []);

  const ping = useCallback(async (force = false) => {
    const current = readState();
    const now = Date.now();
    if (current.until <= now) {
      if (current.until) saveState(disabledState);
      setState(disabledState);
      return;
    }
    if (!force && current.lastAttemptAt !== null && now - current.lastAttemptAt < PING_INTERVAL_MS) return;

    const attempt = { ...current, lastAttemptAt: now };
    saveState(attempt);
    setState(attempt);
    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;
    try {
      const response = await fetch(healthUrl(), { method: "GET", cache: "no-store", signal: controller.signal });
      const latest = readState();
      if (latest.until <= Date.now()) return;
      const result: KeepAwakeState = {
        ...latest,
        lastResult: response.ok ? "ok" : "error",
        lastStatus: response.status,
      };
      saveState(result);
      setState(result);
    } catch {
      if (controller.signal.aborted) return;
      const latest = readState();
      if (latest.until <= Date.now()) return;
      const result = { ...latest, lastResult: "error" as const, lastStatus: null };
      saveState(result);
      setState(result);
    }
  }, []);

  const stop = useCallback(() => {
    controllerRef.current?.abort();
    saveState(disabledState);
    setState(disabledState);
  }, []);

  const start = useCallback(() => {
    const active = { ...disabledState, until: Date.now() + MAX_DURATION_MS };
    saveState(active);
    setState(active);
    void ping(true);
  }, [ping]);

  useEffect(() => {
    if (!enabled) {
      controllerRef.current?.abort();
      return;
    }
    refresh();
    const onChange = () => refresh();
    const onVisible = () => {
      if (document.visibilityState === "visible") void ping();
    };
    window.addEventListener("storage", onChange);
    window.addEventListener("platform-keep-awake-change", onChange);
    document.addEventListener("visibilitychange", onVisible);
    const pingTimer = window.setInterval(() => void ping(), PING_INTERVAL_MS);
    const clockTimer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => {
      window.clearInterval(pingTimer);
      window.clearInterval(clockTimer);
      window.removeEventListener("storage", onChange);
      window.removeEventListener("platform-keep-awake-change", onChange);
      document.removeEventListener("visibilitychange", onVisible);
      controllerRef.current?.abort();
    };
  }, [enabled, ping, refresh]);

  useEffect(() => {
    if (enabled && state.until > 0 && state.until <= now) stop();
  }, [enabled, now, state.until, stop]);

  if (!enabled || !showControls) return null;
  const active = state.until > now;

  return <Card className="fixed bottom-4 right-4 z-50 w-[min(24rem,calc(100vw-2rem))] shadow-lg">
    <CardHeader>
      <div className="flex items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2"><Activity className="size-4" aria-hidden="true" /> Demo backend</CardTitle>
        <Badge variant={active ? "secondary" : "outline"}>{active ? "Keep-awake on" : "Sleeping allowed"}</Badge>
      </div>
      <CardDescription>Send a lightweight health request every 10 minutes. Automatically stops after 72 hours.</CardDescription>
    </CardHeader>
    <CardContent className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        {active
          ? `Up to ${remainingLabel(state.until, now)} remaining · ${state.lastAttemptAt ? `Last ping ${state.lastResult === "ok" ? "succeeded" : state.lastResult === "error" ? "failed" : "started"}` : "Starting first ping"}${state.lastStatus ? ` (HTTP ${state.lastStatus})` : ""}. Keep this signed-in dashboard open.`
          : "Only a platform administrator can run this. Closing the browser, losing connectivity, or background-tab throttling can still let the free service sleep."}
      </p>
      {active
        ? <Button variant="outline" onClick={stop}><Square data-icon="inline-start" />Stop keep-awake</Button>
        : <Button onClick={start}><Activity data-icon="inline-start" />Keep awake for 72 hours</Button>}
    </CardContent>
  </Card>;
}
