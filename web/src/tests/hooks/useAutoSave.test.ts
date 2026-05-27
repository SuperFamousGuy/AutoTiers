import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
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
});
