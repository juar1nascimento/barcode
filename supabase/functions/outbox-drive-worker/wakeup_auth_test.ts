import { assertEquals } from "jsr:@std/assert@1";
import { constantTimeSecretMatch } from "./wakeup_auth.ts";

Deno.test("wake-up auth fails closed when secret is missing or weak", () => {
  assertEquals(constantTimeSecretMatch("x".repeat(40), undefined), false);
  assertEquals(constantTimeSecretMatch("short", "short"), false);
  assertEquals(constantTimeSecretMatch(null, "x".repeat(40)), false);
});

Deno.test("wake-up auth accepts exact secret only", () => {
  const secret = "gti-test-secret-".repeat(3);
  assertEquals(constantTimeSecretMatch(secret, secret), true);
  assertEquals(constantTimeSecretMatch(secret + "x", secret), false);
  assertEquals(constantTimeSecretMatch("z" + secret.slice(1), secret), false);
});
