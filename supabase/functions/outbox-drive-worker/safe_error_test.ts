import { assertEquals } from "jsr:@std/assert@1";
import { safeError } from "./safe_error.ts";

Deno.test("redacts signed URLs and their query tokens", () => {
  const output = safeError(
    new Error(
      "storage request failed: https://example.supabase.co/storage/v1/object/sign/private/photo.jpg?token=jwt.secret.signature",
    ),
  );
  assertEquals(output.includes("example.supabase.co"), false);
  assertEquals(output.includes("jwt.secret.signature"), false);
  assertEquals(output.includes("[REDACTED_URL]"), true);
});

Deno.test("redacts bearer tokens and named secret assignments", () => {
  const output = safeError(
    "Authorization: Bearer super-secret token=private123 client_secret=oauth-secret",
  );
  assertEquals(output.includes("super-secret"), false);
  assertEquals(output.includes("private123"), false);
  assertEquals(output.includes("oauth-secret"), false);
  assertEquals(output.includes("Bearer [REDACTED]"), true);
  assertEquals(output.includes("token=[REDACTED]"), true);
});

Deno.test("flattens multiline errors and caps error detail length", () => {
  assertEquals(safeError("first line\nsecond line"), "first line second line");
  assertEquals(safeError("x".repeat(600)).length, 500);
});

Deno.test("redacts PEM blocks", () => {
  const pem = "key: -----BEGIN " + "PRIVATE KEY-----private-material-----END " + "PRIVATE KEY-----";
  const output = safeError(pem);
  assertEquals(output.includes("private-material"), false);
  assertEquals(output.includes("[REDACTED_PEM]"), true);
});
