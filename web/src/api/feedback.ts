import { apiFetch } from "./client";

/** Triage category a user can tag their feedback with. Wire values match the
 * backend FeedbackCategory enum. "idea" is the default when none is chosen. */
export type FeedbackCategory = "bug" | "idea" | "other";

/**
 * Submit in-app feedback. The backend emails it to a fixed team inbox.
 * Resolves on 202; throws ApiError on failure (422 validation, 429
 * rate-limit, 502 transport). The success detail string is discarded —
 * no caller consumes it.
 *
 * The response is a JSON body ({ detail }), so apiFetch (which parses JSON)
 * is correct here — this is NOT an empty-body 204 like logout().
 *
 * `category` is sent in the POST body. The backend treats it as optional with
 * a server-side default of "idea", so callers may omit it; this client always
 * sends it (defaulting to "idea") to keep the wire shape explicit.
 */
export async function sendFeedback(
  message: string,
  category: FeedbackCategory = "idea",
): Promise<void> {
  await apiFetch<{ detail: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify({ message, category }),
  });
}
