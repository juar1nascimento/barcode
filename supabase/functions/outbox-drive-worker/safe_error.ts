const URL_PATTERN = /https?:\/\/[^\s"'<>]+/gi;
const PEM_PATTERN = /-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----/g;
const BEARER_PATTERN = /\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi;
const SECRET_ASSIGNMENT_PATTERN =
  /\b(token|access_token|refresh_token|client_secret|service_role|api[_-]?key|apikey|signature|x-goog-signature|x-amz-signature)\s*([=:])\s*["']?[^&\s,"'<>]+/gi;

/**
 * Redact credentials and URLs from error details before returning/logging them.
 * This function is for error text only; it must not be used on operational URLs.
 */
export function safeError(error: unknown): string {
  let value = String(
    error instanceof Error ? error.message : error ?? "unknown_error",
  );
  value = value.replace(/[\r\n]+/g, " ");
  value = value.replace(PEM_PATTERN, "[REDACTED_PEM]");
  value = value.replace(BEARER_PATTERN, "Bearer [REDACTED]");
  value = value.replace(SECRET_ASSIGNMENT_PATTERN, "$1$2[REDACTED]");
  value = value.replace(URL_PATTERN, "[REDACTED_URL]");
  return value.slice(0, 500);
}
