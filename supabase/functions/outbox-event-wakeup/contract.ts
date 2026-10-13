/**
 * Contrato puro do sinal de wake-up da outbox GTI SESA.
 *
 * Este módulo não processa outboxes, não chama serviços externos e não executa
 * efeitos colaterais. O payload é apenas um sinal; o worker deve reivindicar
 * itens elegíveis diretamente no PostgreSQL.
 */
export const MAX_WAKEUP_BODY_BYTES = 2048;
export const MAX_WAKEUP_BATCH = 5;

export type WakeupSignal = {
  event: "outbox.wakeup";
  source: "gti-sesa";
  schema_version: 1;
  correlation_id: string;
};

export type WakeupParseResult =
  | { ok: true; signal: WakeupSignal }
  | { ok: false; error: "body_too_large" | "invalid_json" | "invalid_contract" };

export function parseWakeupSignal(raw: string): WakeupParseResult {
  if (new TextEncoder().encode(raw).byteLength > MAX_WAKEUP_BODY_BYTES) {
    return { ok: false, error: "body_too_large" };
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return { ok: false, error: "invalid_json" };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ok: false, error: "invalid_contract" };
  }
  const v = value as Record<string, unknown>;
  const keys = Object.keys(v).sort();
  const expected = ["correlation_id", "event", "schema_version", "source"];
  if (
    keys.length !== expected.length ||
    keys.some((key, index) => key !== expected[index]) ||
    v.event !== "outbox.wakeup" ||
    v.source !== "gti-sesa" ||
    v.schema_version !== 1 ||
    typeof v.correlation_id !== "string" ||
    !/^[a-zA-Z0-9_-]{8,80}$/.test(v.correlation_id)
  ) {
    return { ok: false, error: "invalid_contract" };
  }
  return { ok: true, signal: v as WakeupSignal };
}

/** Compara o segredo sem saída antecipada por byte; segredo ausente falha fechado. */
export function isWakeupAuthorized(
  authorizationHeader: string | null,
  expectedSecret: string | undefined,
): boolean {
  if (!expectedSecret || expectedSecret.length < 32 || !authorizationHeader) return false;
  const prefix = "Bearer ";
  if (!authorizationHeader.startsWith(prefix)) return false;
  const provided = new TextEncoder().encode(authorizationHeader.slice(prefix.length));
  const expected = new TextEncoder().encode(expectedSecret);
  if (provided.length !== expected.length) return false;
  let difference = 0;
  for (let i = 0; i < expected.length; i++) difference |= provided[i] ^ expected[i];
  return difference === 0;
}
