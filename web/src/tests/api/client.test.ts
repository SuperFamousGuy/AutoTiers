import { describe, it, expect, vi, afterEach } from "vitest";
import { ApiError, TimeoutError, apiFetch } from "@/api/client";

describe("ApiError", () => {
  it("preserves status and sets name", () => {
    const err = new ApiError(404, "not found");
    expect(err.status).toBe(404);
    expect(err.message).toBe("not found");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("TimeoutError", () => {
  it("is an ApiError with status 0 and a distinguishable name", () => {
    const err = new TimeoutError(30_000);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toBeInstanceOf(TimeoutError);
    expect(err.status).toBe(0);
    expect(err.name).toBe("TimeoutError");
    expect(err.timeoutMs).toBe(30_000);
    expect(err.message).toBe("Request timed out after 30000ms");
  });
});

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed JSON on a 2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, count: 3 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiFetch<{ ok: boolean; count: number }>("/api/test");

    expect(result).toEqual({ ok: true, count: 3 });
  });

  it("throws ApiError with body text on non-2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("rule validation failed", { status: 422 }),
    );

    await expect(apiFetch("/api/generate")).rejects.toMatchObject({
      status: 422,
      message: "rule validation failed",
      name: "ApiError",
    });
  });

  it("falls back to statusText when body is empty", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("", { status: 500, statusText: "Internal Server Error" }),
    );

    await expect(apiFetch("/api/whatever")).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });

  it("rejects with TimeoutError when fetch never resolves before the timeout", async () => {
    // A fetch that never resolves on its own, but honors the abort signal the
    // way a real browser fetch does.
    vi.spyOn(global, "fetch").mockImplementation(
      (_url, opts?: RequestInit) =>
        new Promise((_resolve, reject) => {
          const signal = opts?.signal;
          signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }),
    );

    const err = await apiFetch("/api/generate", undefined, 20).catch((e) => e);
    expect(err).toBeInstanceOf(TimeoutError);
    expect((err as TimeoutError).timeoutMs).toBe(20);
    expect((err as TimeoutError).status).toBe(0);
  });

  it("passes an abort signal to fetch and clears the timer on success", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const setTimeoutSpy = vi.spyOn(global, "setTimeout");
    const clearTimeoutSpy = vi.spyOn(global, "clearTimeout");

    await apiFetch("/api/test");

    const passedInit = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(passedInit.signal).toBeInstanceOf(AbortSignal);
    expect(passedInit.signal?.aborted).toBe(false);

    // The timeout timer must actually be cleared on success — otherwise a
    // late-firing timer could abort an already-completed request. Assert the
    // exact timer created by apiFetch was passed to clearTimeout.
    const timerId = setTimeoutSpy.mock.results[0].value;
    expect(clearTimeoutSpy).toHaveBeenCalledWith(timerId);
  });

  it("aborts immediately when a caller-supplied signal is already aborted", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation(
      (_url, opts?: RequestInit) =>
        new Promise((resolve, reject) => {
          const signal = opts?.signal;
          if (signal?.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
          resolve(new Response("{}", { status: 200 }));
        }),
    );

    const controller = new AbortController();
    controller.abort();

    const err = await apiFetch("/api/test", { signal: controller.signal }).catch(
      (e) => e,
    );

    // Caller cancellation surfaces as the original AbortError, NOT a TimeoutError.
    expect(err).not.toBeInstanceOf(TimeoutError);
    expect((err as DOMException).name).toBe("AbortError");
    const passedInit = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(passedInit.signal?.aborted).toBe(true);
  });

  it("aborts when a caller-supplied signal fires mid-flight (composed with timeout)", async () => {
    vi.spyOn(global, "fetch").mockImplementation(
      (_url, opts?: RequestInit) =>
        new Promise((_resolve, reject) => {
          const signal = opts?.signal;
          signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );

    const controller = new AbortController();
    // Generous timeout so the caller abort — not the timer — is what fires.
    const promise = apiFetch("/api/test", { signal: controller.signal }, 10_000);
    controller.abort();

    const err = await promise.catch((e) => e);
    expect(err).not.toBeInstanceOf(TimeoutError);
    expect((err as DOMException).name).toBe("AbortError");
  });
});
