import type { Api } from "./api";

export type RuntimeReadiness = {
  state: "starting" | "ready" | "busy" | "unavailable";
  retry_after_seconds: number;
  code?: string | null;
};

/** Retry only this read-only probe; preparation POSTs are never retried here. */
export async function waitForRuntime(
  api: Api,
  signal: AbortSignal,
  timing = { deadlineMs: 120_000, pollMs: 3_000 },
): Promise<void> {
  const timeout = AbortSignal.timeout(timing.deadlineMs);
  const bounded = AbortSignal.any([signal, timeout]);
  try {
    while (true) {
      bounded.throwIfAborted();
      const result = await api<RuntimeReadiness>("/runtime-readiness", {
        signal: bounded,
      });
      bounded.throwIfAborted();
      if (result.state === "ready") return;
      if (result.state === "unavailable") {
        throw new Error(
          `Voice runtime unavailable (${result.code ?? "unknown"}).`,
        );
      }
      await new Promise<void>((resolve, reject) => {
        const abort = () => {
          clearTimeout(timer);
          reject(bounded.reason);
        };
        const timer = setTimeout(() => {
          bounded.removeEventListener("abort", abort);
          resolve();
        }, timing.pollMs);
        bounded.addEventListener("abort", abort, { once: true });
        if (bounded.aborted) abort();
      });
    }
  } catch (error) {
    if (timeout.aborted && !signal.aborted) {
      throw new Error(
        "Voice runtime did not become ready within two minutes. Try again later.",
      );
    }
    throw error;
  }
}
