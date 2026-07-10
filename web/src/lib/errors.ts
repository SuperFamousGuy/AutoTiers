import { ApiError, TimeoutError } from "@/api/client";

/**
 * FastAPI reports errors as JSON: `{"detail": "..."}` for a raised HTTPException
 * and `{"detail": [{"loc": ..., "msg": "...", "type": ...}]}` for request-body
 * validation failures (e.g. the score-weight sum validator in
 * backend/app/schemas/generate.py). `apiFetch` stores that raw body as
 * `ApiError.message`, so surfacing it verbatim would show the user a JSON blob.
 * Pull out the human-readable detail/msg when the body is structured, and fall
 * back to the raw string only when it isn't JSON we recognise.
 */
function extractApiErrorMessage(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed || (!trimmed.startsWith("{") && !trimmed.startsWith("["))) {
    return trimmed;
  }
  try {
    const detail = (JSON.parse(trimmed) as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) =>
          d && typeof (d as { msg?: unknown }).msg === "string"
            ? (d as { msg: string }).msg.trim()
            : "",
        )
        .filter(Boolean);
      if (msgs.length) return msgs.join(" ");
    }
  } catch {
    // Not JSON after all — fall through to the raw string below.
  }
  return trimmed;
}

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
    // meant to be read — extract it, unwrapping FastAPI's JSON envelope when the
    // body is structured, and pass it through when present.
    const message = extractApiErrorMessage(error.message);
    if (message) return message;
    return `The request failed (${error.status}).`;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return "Something went wrong. Please try again.";
}
