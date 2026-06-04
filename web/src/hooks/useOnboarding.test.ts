import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useOnboarding } from "./useOnboarding";

describe("useOnboarding", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows the guidance on a fresh first run (empty storage)", () => {
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.showOnboarding).toBe(true);
  });

  it("hides the guidance for a returning user who already dismissed it", () => {
    localStorage.setItem("onboarding_seen", "1");
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.showOnboarding).toBe(false);
  });

  it("dismiss hides the card and persists the seen flag", () => {
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.showOnboarding).toBe(true);

    act(() => {
      result.current.dismiss();
    });

    expect(result.current.showOnboarding).toBe(false);
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("reopen re-shows the card without clearing the seen flag", () => {
    const { result } = renderHook(() => useOnboarding());
    act(() => result.current.dismiss());
    expect(result.current.showOnboarding).toBe(false);

    act(() => result.current.reopen());
    expect(result.current.showOnboarding).toBe(true);
    // seen flag persists — a future page load still starts hidden
    expect(localStorage.getItem("onboarding_seen")).toBe("1");
  });

  it("shows the guidance (does not crash) when localStorage.getItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.showOnboarding).toBe(true);
    spy.mockRestore();
  });

  it("dismiss does not crash when localStorage.setItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const { result } = renderHook(() => useOnboarding());
    act(() => {
      result.current.dismiss();
    });
    // still hidden for the session even though persistence failed
    expect(result.current.showOnboarding).toBe(false);
    spy.mockRestore();
  });

  it("treats any non-'1' stored value as not-seen", () => {
    localStorage.setItem("onboarding_seen", "true");
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.showOnboarding).toBe(true);
  });
});
