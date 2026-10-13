import { assertEquals } from "jsr:@std/assert@1";
import { handleWakeupRequest } from "./handler.ts";
import { createWorkerDispatcher } from "./dispatcher.ts";
import { constantTimeSecretMatch } from "../outbox-drive-worker/wakeup_auth.ts";

// End-to-end in-memory harness: no network, database, secrets, Drive, or production outbox.
Deno.test("isolated wake-up path validates signal, authenticates worker request, and caps batch", async () => {
  const secret = "gti-isolated-test-secret-" + "x".repeat(40);
  const serviceKey = "test-only-service-role-key";
  let workerCalls = 0;
  let workerBody: Record<string, unknown> | undefined;

  const dispatch = createWorkerDispatcher({
    enabled: true,
    supabaseUrl: "https://isolated-test.supabase.co",
    serviceRoleKey: serviceKey,
    wakeupSecret: secret,
  }, async (input, init) => {
    workerCalls++;
    assertEquals(String(input), "https://isolated-test.supabase.co/functions/v1/outbox-drive-worker");
    const headers = new Headers(init?.headers);
    assertEquals(headers.get("authorization"), "Bearer " + serviceKey);
    assertEquals(constantTimeSecretMatch(headers.get("x-gti-wakeup-secret"), secret), true);
    workerBody = JSON.parse(String(init?.body));
    assertEquals(workerBody?.mode, "wakeup");
    assertEquals(workerBody?.limit, 5);
    return Response.json({ ok: true, mode: "process", claimed_changes: 0, synced_changes: 0 });
  });

  const request = new Request("https://isolated-test.supabase.co/functions/v1/outbox-event-wakeup", {
    method: "POST",
    headers: {
      authorization: "Bearer test-gateway-key",
      "x-gti-wakeup-secret": secret,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      event: "outbox.wakeup",
      source: "gti-sesa",
      schema_version: 1,
      correlation_id: "isolated_test_20261013",
    }),
  });

  const response = await handleWakeupRequest(request, secret, dispatch);
  assertEquals(response.status, 202);
  assertEquals(workerCalls, 1);
  assertEquals(workerBody?.correlation_id, "isolated_test_20261013");
});

Deno.test("isolated wake-up rejects bad secret before any worker call", async () => {
  const secret = "gti-isolated-test-secret-" + "x".repeat(40);
  let workerCalls = 0;
  const dispatch = async () => { workerCalls++; };
  const request = new Request("https://isolated-test.invalid", {
    method: "POST",
    headers: { "x-gti-wakeup-secret": "wrong-secret" },
    body: JSON.stringify({
      event: "outbox.wakeup",
      source: "gti-sesa",
      schema_version: 1,
      correlation_id: "isolated_test_20261013",
    }),
  });
  const response = await handleWakeupRequest(request, secret, dispatch);
  assertEquals(response.status, 401);
  assertEquals(workerCalls, 0);
});
