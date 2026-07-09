import { ApiError, TimeoutError } from "@/api/client";

/**
 * Turns whatever a mutation/query threw into a short, user-facing sentence for a
 * Generate failure. `apiFetch` only ever rejects with `ApiError` (any non-2xx),
 * `TimeoutError` (the 30s client timeout), or a raw `TypeError`/`AbortError` from
 * `fetch` itself (network blip, DNS failure). Keep the copy blame-free and
 * actionable — the user should know it failed and that retrying is worthwhile.
 */
export function describeGenerateError(error: unknown): string {
  if (error instanceof TimeoutError) {
    return "The request timed out. Check your connection and try again.";
  }
  if (error instanceof ApiError) {
    // A 5xx is a server-side failure — its raw body (often an HTML error page or
    // stack trace) is noise to the user, so surface a generic line instead.
    if (error.status >= 500) {
      return "The server ran into a problem building your tiers. Please try again.";
    }
    // A 4xx (e.g. a weight-tolerance / validation rejection) carries a message
    // meant to be read — pass it through when present.
    const message = error.message.trim();
    if (message) return message;
    return `The request failed (${error.status}).`;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return "Something went wrong. Please try again.";
}
