import { assertEquals, assertRejects } from "jsr:@std/assert@1";
import { createWorkerDispatcher } from "./dispatcher.ts";
import type { WakeupSignal } from "./contract.ts";

const signal: WakeupSignal = {
  event: "outbox.wakeup",
  source: "gti-sesa",
  schema_version: 1,
  correlation_id: "test_corr_20261013",
};

Deno.test("dispatcher is disabled by default and makes no request", async () => {
  let calls = 0;
  const dispatch = createWorkerDispatcher({}, async () => {
    calls++;
    return Response.json({ ok: true, mode: "process", claimed_changes: 0 });
  });
  await assertRejects(() => dispatch(signal), Error, "wakeup_dispatch_disabled");
  assertEquals(calls, 0);
});

Deno.test("dispatcher refuses invalid configuration before network call", async () => {
  let calls = 0;
  const dispatch = createWorkerDispatcher({
    enabled: true,
    supabaseUrl: "http://localhost:54321",
    serviceRoleKey: "test",
    wakeupSecret: "x".repeat(40),
  }, async () => {
    calls++;
    return Response.json({});
  });
  await assertRejects(() => dispatch(signal), Error, "wakeup_dispatch_configuration_invalid");
  assertEquals(calls, 0);
});

Deno.test("dispatcher calls only the fixed worker with a batch capped at five", async () => {
  let seenUrl = "";
  let seenInit: RequestInit | undefined;
  const dispatch = createWorkerDispatcher({
    enabled: true,
    supabaseUrl: "https://example.supabase.co",
    serviceRoleKey: "test-service-key",
    wakeupSecret: "gti-wakeup-test-secret-".repeat(2),
  }, async (input, init) => {
    seenUrl = String(input);
    seenInit = init;
    return Response.json({ ok: true, mode: "process", claimed_changes: 5, synced_changes: 5 });
  });
  await dispatch(signal);
  assertEquals(seenUrl, "https://example.supabase.co/functions/v1/outbox-drive-worker");
  assertEquals((seenInit?.headers as Record<string, string>)["x-gti-wakeup-secret"], "gti-wakeup-test-secret-".repeat(2));
  const body = JSON.parse(String(seenInit?.body));
  assertEquals(body.mode, "wakeup");
  assertEquals(body.limit, 5);
  assertEquals(body.correlation_id, signal.correlation_id);
});

Deno.test("dispatcher rejects worker errors and over-limit responses", async () => {
  const config = {
    enabled: true,
    supabaseUrl: "https://example.supabase.co",
    serviceRoleKey: "test-service-key",
    wakeupSecret: "gti-wakeup-test-secret-".repeat(2),
  };
  const failed = createWorkerDispatcher(config, async () => new Response("no", { status: 500 }));
  await assertRejects(() => failed(signal), Error, "wakeup_worker_rejected");
  const overLimit = createWorkerDispatcher(config, async () =>
    Response.json({ ok: true, mode: "process", claimed_changes: 6 })
  );
  await assertRejects(() => overLimit(signal), Error, "wakeup_worker_invalid_response");
});
