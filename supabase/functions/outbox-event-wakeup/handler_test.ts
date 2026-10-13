import { handleWakeupRequest } from "./handler.ts";

const secret = "gti-wakeup-secret-" + "s".repeat(40);
const payload = JSON.stringify({
  event: "outbox.wakeup",
  source: "gti-sesa",
  schema_version: 1,
  correlation_id: "event_20261013",
});

function request(method = "POST", body = payload, token = secret) {
  return new Request("https://example.test/outbox-event-wakeup", {
    method,
    headers: {
      authorization: "Bearer test-gateway-service-key",
      "x-gti-wakeup-secret": token === null ? "" : token,
      "content-type": "application/json",
    },
    body: method === "GET" ? undefined : body,
  });
}

Deno.test("receiver rejects methods other than POST", async () => {
  const response = await handleWakeupRequest(request("GET"), secret);
  if (response.status !== 405) throw new Error("expected 405");
});

Deno.test("receiver rejects missing or incorrect credentials before reading payload", async () => {
  const response = await handleWakeupRequest(request("POST", payload, "wrong-secret"), secret);
  if (response.status !== 401) throw new Error("expected 401");
});

Deno.test("receiver rejects malformed payload", async () => {
  const response = await handleWakeupRequest(request("POST", "{"), secret);
  if (response.status !== 400) throw new Error("expected 400");
});

Deno.test("receiver enforces bounded request body", async () => {
  const response = await handleWakeupRequest(request("POST", "x".repeat(2049)), secret);
  if (response.status !== 413) throw new Error("expected 413");
});

Deno.test("receiver does not acknowledge a valid signal without a dispatcher", async () => {
  const response = await handleWakeupRequest(request(), secret);
  if (response.status !== 503) throw new Error("must fail closed without dispatcher");
  const body = await response.json();
  if (body.error !== "wakeup_dispatch_not_configured") throw new Error("wrong fail-closed response");
});

Deno.test("receiver dispatches only validated signals", async () => {
  let received = "";
  const response = await handleWakeupRequest(request(), secret, async (signal) => {
    received = signal.correlation_id;
  });
  if (response.status !== 202) throw new Error("expected 202");
  if (received !== "event_20261013") throw new Error("validated signal not dispatched");
});

Deno.test("receiver fails closed when dispatcher throws", async () => {
  const response = await handleWakeupRequest(request(), secret, async () => {
    throw new Error("internal detail must not escape");
  });
  if (response.status !== 503) throw new Error("expected 503");
  const body = await response.text();
  if (body.includes("internal detail")) throw new Error("internal error leaked");
});
