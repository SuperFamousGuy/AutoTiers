import { useCallback, useState } from "react";
import { ApiError } from "@/api/client";
import { extractApiErrorMessage } from "@/lib/errors";

/**
 * Turn a thrown value into a short, user-facing message.
 *
 * This is the extraction the six provider-connect forms hand-rolled inline:
 * an `ApiError` (any non-2xx, or the client `TimeoutError`) carries a body meant
 * to be read, so unwrap FastAPI's `{"detail": ...}` / validation envelope with
 * the shared {@link extractApiErrorMessage} rather than surfacing the raw JSON
 * blob (the root cause behind #693/#642/#483). Anything else — a network blip,
 * an empty extracted body — falls back to the caller's message.
 */
export function toActionErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return extractApiErrorMessage(error.message) || fallback;
  }
  return fallback;
}

/** Options controlling how {@link AsyncAction.run} turns a failure into copy. */
export interface RunOptions {
  /**
   * Message shown when the thrown value isn't an `ApiError`, or its extracted
   * body is empty. Defaults to a generic "something went wrong" line.
   */
  fallback?: string;
  /**
   * Fully override how a thrown value becomes a message, for the rare call site
   * whose failure copy doesn't follow the extract-or-fallback shape.
   */
  mapError?: (error: unknown) => string;
}

export interface AsyncAction {
  /** True while a `run` call is in flight. Drive `disabled=` and spinners off this. */
  pending: boolean;
  /** The last failure's user-facing message, or `null`. Cleared at the start of every `run`. */
  error: string | null;
  /**
   * Wrap an async unit of work: clear the error, flip `pending` on, await `fn`,
   * and on a throw extract a user-facing message into `error`. Resolves to `fn`'s
   * value on success, or `undefined` when it threw (so callers can guard the
   * happy path without a second try/catch). `pending` is always reset, even on
   * failure. `fn` may call `setError` itself to report a non-throwing failure
   * (e.g. a lookup that succeeded but found nothing) — that message survives.
   */
  run: <T>(fn: () => Promise<T>, options?: RunOptions) => Promise<T | undefined>;
  /** Set (or clear, with `null`) the error message directly. Stable across renders. */
  setError: (message: string | null) => void;
  /** Clear the error without running anything. Stable across renders. */
  reset: () => void;
}

const DEFAULT_FALLBACK = "Something went wrong. Please try again.";

/**
 * Standardizes the `busy`/`error`/try-catch-finally dance the provider-connect
 * forms each re-implemented with independent `useState` calls. One instance owns
 * one `pending` flag and one `error` string; share a single instance across
 * sibling actions (e.g. Refresh + Disconnect) so either in-flight action
 * disables both and reports into the same error slot, matching the pre-refactor
 * behavior.
 */
export function useAsyncAction(): AsyncAction {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(fn: () => Promise<T>, options?: RunOptions): Promise<T | undefined> => {
      setError(null);
      setPending(true);
      try {
        return await fn();
      } catch (e) {
        setError(
          options?.mapError
            ? options.mapError(e)
            : toActionErrorMessage(e, options?.fallback ?? DEFAULT_FALLBACK),
        );
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  const reset = useCallback(() => setError(null), []);

  return { pending, error, run, setError, reset };
}
