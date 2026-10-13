import {
  isWakeupAuthorized,
  MAX_WAKEUP_BODY_BYTES,
  parseWakeupSignal,
  type WakeupSignal,
} from "./contract.ts";

type Dispatch = (signal: WakeupSignal) => Promise<void>;

const json = (body: Record<string, unknown>, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });

async function readBoundedBody(req: Request): Promise<string | null> {
  const declared = req.headers.get("content-length");
  if (declared && /^\d+$/.test(declared) && Number(declared) > MAX_WAKEUP_BODY_BYTES) {
    return null;
  }
  if (!req.body) return "";
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_WAKEUP_BODY_BYTES) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return "\u0000invalid-utf8";
  }
}

/** Receiver boundary: gateway auth is separate from the dedicated wake-up secret. */
export async function handleWakeupRequest(
  req: Request,
  expectedSecret: string | undefined,
  dispatch?: Dispatch,
): Promise<Response> {
  if (req.method !== "POST") {
    return json({ ok: false, error: "method_not_allowed" }, 405);
  }
  if (!isWakeupAuthorized(`Bearer ${req.headers.get("x-gti-wakeup-secret") ?? ""}`, expectedSecret)) {
    return json({ ok: false, error: "unauthorized" }, 401);
  }
  const raw = await readBoundedBody(req);
  if (raw === null) return json({ ok: false, error: "body_too_large" }, 413);
  const parsed = parseWakeupSignal(raw);
  if (!parsed.ok) {
    const status = parsed.error === "body_too_large" ? 413 : 400;
    return json({ ok: false, error: parsed.error }, status);
  }
  if (!dispatch) {
    return json({ ok: false, error: "wakeup_dispatch_not_configured" }, 503);
  }
  try {
    await dispatch(parsed.signal);
  } catch {
    return json({ ok: false, error: "wakeup_dispatch_failed" }, 503);
  }
  return json({ ok: true, accepted: true, correlation_id: parsed.signal.correlation_id }, 202);
}
