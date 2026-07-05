export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/**
 * Default request timeout for every apiFetch call. Browser fetch has no
 * built-in timeout, so without this a hung backend (or a slow proxied call to
 * Yahoo/ESPN/Sleeper) would leave callers spinning forever with no error.
 */
export const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Thrown when a request exceeds its timeout. Extends ApiError with status 0 so
 * existing `instanceof ApiError` handlers surface its message instead of a
 * generic fallback, while `instanceof TimeoutError` (or `status === 0`) lets
 * callers show a dedicated "request timed out" state.
 */
export class TimeoutError extends ApiError {
  constructor(public readonly timeoutMs: number) {
    super(0, `Request timed out after ${timeoutMs}ms`);
    this.name = "TimeoutError";
  }
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const callerSignal = init?.signal;

  // Compose any caller-supplied signal with our internal timeout signal: if the
  // caller aborts, we abort too (propagating their reason).
  const onCallerAbort = () => controller.abort(callerSignal?.reason);
  if (callerSignal) {
    if (callerSignal.aborted) {
      controller.abort(callerSignal.reason);
    } else {
      callerSignal.addEventListener("abort", onCallerAbort, { once: true });
    }
  }

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const resp = await fetch(`${API_URL}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
      // Placed after `...init` so our composed signal always wins.
      signal: controller.signal,
    });
    if (!resp.ok) {
      const body = await resp.text();
      throw new ApiError(resp.status, body || resp.statusText);
    }
    return resp.json() as Promise<T>;
  } catch (err) {
    // Distinguish our own timeout from a caller-initiated cancellation: only the
    // timer sets `timedOut`. A caller abort rethrows the original AbortError so
    // callers can tell "I cancelled this" apart from "it timed out".
    if (timedOut) {
      throw new TimeoutError(timeoutMs);
    }
    throw err;
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", onCallerAbort);
  }
}
