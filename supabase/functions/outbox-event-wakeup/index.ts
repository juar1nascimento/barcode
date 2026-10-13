import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { handleWakeupRequest } from "./handler.ts";

// No dispatcher is connected in this gate. The endpoint is deliberately fail-closed.
Deno.serve((req: Request) =>
  handleWakeupRequest(req, Deno.env.get("GTI_OUTBOX_WAKEUP_SECRET"))
);
