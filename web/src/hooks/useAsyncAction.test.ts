import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAsyncAction, toActionErrorMessage } from "./useAsyncAction";
import { ApiError, TimeoutError } from "@/api/client";

describe("toActionErrorMessage", () => {
  it("unwraps FastAPI's JSON detail envelope from an ApiError", () => {
    const err = new ApiError(401, '{"detail":"This ESPN league is private."}');
    expect(toActionErrorMessage(err, "fallback")).toBe("This ESPN league is private.");
  });

  it("falls back for an ApiError whose extracted body is empty", () => {
    expect(toActionErrorMessage(new ApiError(500, ""), "Connect failed.")).toBe("Connect failed.");
  });

  it("surfaces a TimeoutError's message (it is an ApiError subclass)", () => {
    // Not JSON, so extractApiErrorMessage returns it verbatim.
    expect(toActionErrorMessage(new TimeoutError(30_000), "fallback")).toMatch(/timed out/i);
  });

  it("falls back for a non-ApiError throw (network blip)", () => {
    expect(toActionErrorMessage(new Error("network down"), "Refresh failed.")).toBe(
      "Refresh failed.",
    );
  });
});

describe("useAsyncAction", () => {
  it("starts idle with no error", () => {
    const { result } = renderHook(() => useAsyncAction());
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("flips pending true while the work is in flight, then back to false", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    let runPromise: Promise<unknown>;
    act(() => {
      runPromise = result.current.run(() => gate);
    });
    // Synchronously after kicking off run, we are pending.
    await waitFor(() => expect(result.current.pending).toBe(true));
    expect(result.current.error).toBeNull();

    await act(async () => {
      release();
      await runPromise;
    });
    expect(result.current.pending).toBe(false);
  });

  it("returns the resolved value on success and leaves error null", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let returned: unknown;
    await act(async () => {
      returned = await result.current.run(async () => "ok");
    });
    expect(returned).toBe("ok");
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);
  });

  it("extracts an ApiError body into error and resolves to undefined on failure", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let returned: unknown = "sentinel";
    await act(async () => {
      returned = await result.current.run(
        async () => {
          throw new ApiError(401, '{"detail":"Cookies expired."}');
        },
        { fallback: "Refresh failed." },
      );
    });
    expect(returned).toBeUndefined();
    expect(result.current.error).toBe("Cookies expired.");
    expect(result.current.pending).toBe(false);
  });

  it("uses the fallback for a non-ApiError throw", async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => {
      await result.current.run(
        async () => {
          throw new Error("boom");
        },
        { fallback: "Connect failed. Please try again." },
      );
    });
    expect(result.current.error).toBe("Connect failed. Please try again.");
  });

  it("honors a mapError override for bespoke failure copy", async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => {
      await result.current.run(
        async () => {
          throw new ApiError(500, '{"detail":"raw"}');
        },
        { mapError: () => "Couldn't reach Sleeper. Please try again." },
      );
    });
    // mapError wins over extraction — the raw detail is never surfaced.
    expect(result.current.error).toBe("Couldn't reach Sleeper. Please try again.");
  });

  it("clears a prior error at the start of the next run", async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => {
      await result.current.run(async () => {
        throw new ApiError(500, "boom");
      });
    });
    expect(result.current.error).not.toBeNull();

    await act(async () => {
      await result.current.run(async () => "ok");
    });
    expect(result.current.error).toBeNull();
  });

  it("preserves an error the work sets itself on a non-throwing failure path", async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => {
      await result.current.run(async () => {
        // e.g. a username lookup that succeeded but matched nothing.
        result.current.setError("We couldn't find that Sleeper username.");
      });
    });
    expect(result.current.error).toBe("We couldn't find that Sleeper username.");
    expect(result.current.pending).toBe(false);
  });

  it("setError and reset manage the error slot directly", async () => {
    const { result } = renderHook(() => useAsyncAction());
    act(() => result.current.setError("manual"));
    expect(result.current.error).toBe("manual");
    act(() => result.current.reset());
    expect(result.current.error).toBeNull();
  });
});
