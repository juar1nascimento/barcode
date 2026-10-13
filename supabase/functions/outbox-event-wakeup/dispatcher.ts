import { MAX_WAKEUP_BATCH, type WakeupSignal } from "./contract.ts";

export type DispatchConfig = {
  enabled: boolean;
  supabaseUrl?: string;
  serviceRoleKey?: string;
  wakeupSecret?: string;
};

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function validSupabaseBase(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (
      url.protocol !== "https:" ||
      !url.hostname.endsWith(".supabase.co") ||
      url.username || url.password || url.search || url.hash ||
      (url.pathname !== "/" && url.pathname !== "")
    ) return null;
    return url.origin;
  } catch {
    return null;
  }
}

export function createWorkerDispatcher(
  config: DispatchConfig,
  fetcher: FetchLike = fetch,
): (signal: WakeupSignal) => Promise<void> {
  return async (signal) => {
    if (!config.enabled) throw new Error("wakeup_dispatch_disabled");
    const base = validSupabaseBase(config.supabaseUrl);
    const key = config.serviceRoleKey ?? "";
    const secret = config.wakeupSecret ?? "";
    if (!base || !key || secret.length < 32) {
      throw new Error("wakeup_dispatch_configuration_invalid");
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const response = await fetcher(`${base}/functions/v1/outbox-drive-worker`, {
        method: "POST",
        headers: {
          "authorization": `Bearer ${key}`,
          "content-type": "application/json",
          "x-gti-wakeup-secret": secret,
        },
        body: JSON.stringify({
          mode: "wakeup",
          limit: MAX_WAKEUP_BATCH,
          correlation_id: signal.correlation_id,
        }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("wakeup_worker_rejected");
      let result: unknown;
      try {
        result = await response.json();
      } catch {
        throw new Error("wakeup_worker_invalid_response");
      }
      if (
        !result || typeof result !== "object" ||
        (result as Record<string, unknown>).ok !== true ||
        (result as Record<string, unknown>).mode !== "process" ||
        !Number.isInteger((result as Record<string, unknown>).claimed_changes) ||
        Number((result as Record<string, unknown>).claimed_changes) < 0 ||
        Number((result as Record<string, unknown>).claimed_changes) > MAX_WAKEUP_BATCH
      ) throw new Error("wakeup_worker_invalid_response");
    } finally {
      clearTimeout(timer);
    }
  };
}
