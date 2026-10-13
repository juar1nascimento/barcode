import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { handleWakeupRequest } from "./handler.ts";
import { createWorkerDispatcher } from "./dispatcher.ts";

const dispatchEnabled = Deno.env.get("GTI_OUTBOX_WAKEUP_DISPATCH_ENABLED") === "true";
const dispatch = dispatchEnabled
  ? createWorkerDispatcher({
      enabled: true,
      supabaseUrl: Deno.env.get("SUPABASE_URL"),
      serviceRoleKey: Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"),
      wakeupSecret: Deno.env.get("GTI_OUTBOX_WAKEUP_SECRET"),
    })
  : undefined;

// Disabled unless an operator explicitly enables the feature flag and configures
// the same dedicated secret on both functions. No deploy or secret change here.
Deno.serve((req: Request) =>
  handleWakeupRequest(req, Deno.env.get("GTI_OUTBOX_WAKEUP_SECRET"), dispatch)
);
