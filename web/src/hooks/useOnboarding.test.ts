import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useOnboarding } from "./useOnboarding";

const TOTAL = 5;

describe("useOnboarding (step machine)", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("auto-starts on a fresh first run (empty storage)", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    expect(result.current.active).toBe(true);
    expect(result.current.stepIndex).toBe(0);
  });

  it("stays closed for a returning user who already saw it", () => {
    localStorage.setItem("onboarding_seen", "1");
    const { result } = renderHook(() => useOnboarding(TOTAL));
    expect(result.current.active).toBe(false);
  });

  it("next advances through steps, then finishes and persists on the last step", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.next()); // 0 -> 1
    expect(result.current.stepIndex).toBe(1);
    act(() => result.current.next()); // 1 -> 2
    act(() => result.current.next()); // 2 -> 3
    act(() => result.current.next()); // 3 -> 4 (last)
    expect(result.current.stepIndex).toBe(4);
    expect(result.current.active).toBe(true);
    // next past the last step finishes and persists the seen flag
    act(() => result.current.next());
    expect(result.current.active).toBe(false);
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("back moves to the previous step and clamps at 0", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.goTo(2));
    expect(result.current.stepIndex).toBe(2);
    act(() => result.current.back());
    expect(result.current.stepIndex).toBe(1);
    act(() => result.current.back());
    act(() => result.current.back());
    expect(result.current.stepIndex).toBe(0); // clamped, not negative
  });

  it("goTo clamps to valid range", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.goTo(99));
    expect(result.current.stepIndex).toBe(TOTAL - 1);
    act(() => result.current.goTo(-3));
    expect(result.current.stepIndex).toBe(0);
  });

  it("skip closes the tour AND persists the seen flag (user opted out)", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.skip());
    expect(result.current.active).toBe(false);
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("finish closes the tour AND persists the seen flag", () => {
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.finish());
    expect(result.current.active).toBe(false);
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("start re-opens at step 0 without clearing the seen flag (replay is transient)", () => {
    localStorage.setItem("onboarding_seen", "1");
    const { result } = renderHook(() => useOnboarding(TOTAL));
    expect(result.current.active).toBe(false);
    act(() => result.current.goTo(3));
    act(() => result.current.start());
    expect(result.current.active).toBe(true);
    expect(result.current.stepIndex).toBe(0);
    // seen flag persists — a future page load still starts closed
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("auto-starts (does not crash) when localStorage.getItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    const { result } = renderHook(() => useOnboarding(TOTAL));
    expect(result.current.active).toBe(true);
    spy.mockRestore();
  });

  it("skip does not crash when localStorage.setItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const { result } = renderHook(() => useOnboarding(TOTAL));
    act(() => result.current.skip());
    expect(result.current.active).toBe(false); // closed for the session even though persist failed
    spy.mockRestore();
  });

  it("treats any non-'1' stored value as not-seen", () => {
    localStorage.setItem("onboarding_seen", "true");
    const { result } = renderHook(() => useOnboarding(TOTAL));
    expect(result.current.active).toBe(true);
  });
});
