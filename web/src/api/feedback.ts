import { apiFetch } from "./client";

/**
 * Submit in-app feedback. The backend emails it to a fixed team inbox.
 * Resolves on 202; throws ApiError on failure (422 validation, 429
 * rate-limit, 502 transport). The success detail string is discarded —
 * no caller consumes it.
 *
 * The response is a JSON body ({ detail }), so apiFetch (which parses JSON)
 * is correct here — this is NOT an empty-body 204 like logout().
 */
export async function sendFeedback(message: string): Promise<void> {
  await apiFetch<{ detail: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
