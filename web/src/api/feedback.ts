import { apiFetch } from "./client";

/** Triage category a user can tag their feedback with. Wire values match the
 * backend FeedbackCategory enum. "idea" is the default when none is chosen. */
export type FeedbackCategory = "bug" | "idea" | "other";

/** An optional screenshot to attach to a feedback submission (#287).
 * `base64` is the raw base64 of the image bytes WITHOUT the data-URL prefix. */
export interface FeedbackAttachment {
  base64: string;
  name: string;
  type: string;
}

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
 *
 * `attachment` is optional (#287). When present, the image is sent as base64
 * in the JSON body (NOT multipart — the shared apiFetch is JSON-only) and the
 * backend forwards it inline via SES raw MIME. The backend re-validates type
 * and size; the client validation is a UX nicety, not the gate.
 */
export async function sendFeedback(
  message: string,
  category: FeedbackCategory = "idea",
  attachment?: FeedbackAttachment | null,
): Promise<void> {
  const payload: Record<string, unknown> = { message, category };
  if (attachment) {
    payload.screenshot = attachment.base64;
    payload.screenshot_name = attachment.name;
    payload.screenshot_type = attachment.type;
  }
  await apiFetch<{ detail: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
