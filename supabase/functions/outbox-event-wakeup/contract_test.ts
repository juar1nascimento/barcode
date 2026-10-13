import {
  isWakeupAuthorized,
  MAX_WAKEUP_BODY_BYTES,
  parseWakeupSignal,
} from "./contract.ts";

const valid = JSON.stringify({
  event: "outbox.wakeup",
  source: "gti-sesa",
  schema_version: 1,
  correlation_id: "event_20261013",
});

Deno.test("accepts the minimal valid wake-up signal", () => {
  const result = parseWakeupSignal(valid);
  if (!result.ok) throw new Error("expected valid signal");
  if (result.signal.event !== "outbox.wakeup") throw new Error("wrong event");
});

Deno.test("rejects malformed JSON", () => {
  const result = parseWakeupSignal("{");
  if (result.ok || result.error !== "invalid_json") throw new Error("must reject malformed JSON");
});

Deno.test("rejects unknown fields and business payloads", () => {
  const result = parseWakeupSignal(JSON.stringify({
    event: "outbox.wakeup",
    source: "gti-sesa",
    schema_version: 1,
    correlation_id: "event_20261013",
    patrimonio_id: 123,
  }));
  if (result.ok || result.error !== "invalid_contract") throw new Error("must reject extra fields");
});

Deno.test("rejects invalid correlation identifiers", () => {
  const result = parseWakeupSignal(JSON.stringify({
    event: "outbox.wakeup",
    source: "gti-sesa",
    schema_version: 1,
    correlation_id: "x",
  }));
  if (result.ok) throw new Error("must reject short correlation id");
});

Deno.test("rejects oversized request bodies", () => {
  const result = parseWakeupSignal("x".repeat(MAX_WAKEUP_BODY_BYTES + 1));
  if (result.ok || result.error !== "body_too_large") throw new Error("must enforce body limit");
});

Deno.test("authorization fails closed when secret is missing or weak", () => {
  if (isWakeupAuthorized("Bearer abc", undefined)) throw new Error("missing secret accepted");
  if (isWakeupAuthorized("Bearer abc", "abc")) throw new Error("weak secret accepted");
});

Deno.test("authorization rejects wrong tokens and schemes", () => {
  const secret = "s".repeat(48);
  if (isWakeupAuthorized("Basic " + secret, secret)) throw new Error("wrong scheme accepted");
  if (isWakeupAuthorized("Bearer " + "x".repeat(48), secret)) throw new Error("wrong token accepted");
});

Deno.test("authorization accepts an exact dedicated bearer secret", () => {
  const secret = "gti-wakeup-secret-" + "a".repeat(40);
  if (!isWakeupAuthorized("Bearer " + secret, secret)) throw new Error("valid token rejected");
});
