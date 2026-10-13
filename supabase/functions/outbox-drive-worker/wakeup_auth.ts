/** Internal wake-up guard. Existing scheduled worker modes remain unchanged. */
export function constantTimeSecretMatch(
  provided: string | null,
  expected: string | undefined,
): boolean {
  if (!provided || !expected || expected.length < 32) return false;
  const a = new TextEncoder().encode(provided);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}
