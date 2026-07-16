import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useAutoSave } from "@/hooks/useAutoSave";

describe("useAutoSave", () => {
  it("does not save when no profile is active", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useAutoSave({ activeId: null, payload: { x: 1 }, save, debounceMs: 50 }));
    await new Promise((r) => setTimeout(r, 100));
    expect(save).not.toHaveBeenCalled();
  });

  it("debounces calls, firing once after the window", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ payload }) => useAutoSave({ activeId: "p1", payload, save, debounceMs: 50 }),
      { initialProps: { payload: { x: 1 } } },
    );
    rerender({ payload: { x: 2 } });
    rerender({ payload: { x: 3 } });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenLastCalledWith("p1", { x: 3 });
  });

  it("does not save a stale payload against a just-switched profile", () => {
    vi.useFakeTimers();
    try {
      const save = vi.fn().mockResolvedValue(undefined);
      const payloadA = { x: 1 };
      const { rerender } = renderHook(
        ({ activeId, payload }) => useAutoSave({ activeId, payload, save, debounceMs: 50 }),
        { initialProps: { activeId: "A", payload: payloadA } },
      );
      // Profile switches to B, but hydration lags: payload is still A's.
      rerender({ activeId: "B", payload: payloadA });
      act(() => {
        vi.advanceTimersByTime(200);
      });
      // The stale A payload must never be persisted to profile B.
      expect(save).not.toHaveBeenCalledWith("B", payloadA);
      expect(save).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not start a second save while one is in flight, then fires with the latest payload", async () => {
    let resolveFirst!: () => void;
    const gate = new Promise<void>((r) => { resolveFirst = r; });
    let firstCall = true;
    const save = vi.fn(async () => {
      if (firstCall) {
        firstCall = false;
        await gate; // hold the first PATCH open
      }
    });
    const { rerender } = renderHook(
      ({ payload }) => useAutoSave({ activeId: "p1", payload, save, debounceMs: 10 }),
      { initialProps: { payload: { x: 1 } } },
    );
    rerender({ payload: { x: 2 } });               // arms debounce → fires save A
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenLastCalledWith("p1", { x: 2 });

    // Edit twice more while A is still awaiting the network. The debounce
    // coalesces to x:3; single-flight must keep it queued, not fire concurrently.
    rerender({ payload: { x: 3 } });
    await new Promise((r) => setTimeout(r, 40));
    expect(save).toHaveBeenCalledTimes(1);

    resolveFirst();                                // A settles → queued B fires
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenLastCalledWith("p1", { x: 3 });
  });

  it("resumes autosaving once the payload changes for the switched-to profile", () => {
    vi.useFakeTimers();
    try {
      const save = vi.fn().mockResolvedValue(undefined);
      const payloadA = { x: 1 };
      const { rerender } = renderHook(
        ({ activeId, payload }) => useAutoSave({ activeId, payload, save, debounceMs: 50 }),
        { initialProps: { activeId: "A", payload: payloadA } },
      );
      rerender({ activeId: "B", payload: payloadA }); // switch (stale payload) — no save
      rerender({ activeId: "B", payload: { x: 9 } }); // hydration/edit for B — should save
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(save).toHaveBeenCalledTimes(1);
      expect(save).toHaveBeenCalledWith("B", { x: 9 });
    } finally {
      vi.useRealTimers();
    }
  });
});
