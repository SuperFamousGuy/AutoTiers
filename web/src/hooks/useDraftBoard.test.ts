import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDraftBoard } from "./useDraftBoard";

const KEY = "league-1:standard";

describe("useDraftBoard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("starts with an empty drafted set when storage is empty", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    expect(result.current.draftedCount).toBe(0);
    expect(result.current.drafted.size).toBe(0);
    expect(result.current.isDrafted("123")).toBe(false);
  });

  it("toggleDrafted marks a player drafted", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    expect(result.current.isDrafted("123")).toBe(true);
    expect(result.current.draftedCount).toBe(1);
  });

  it("toggleDrafted again un-drafts the player", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    act(() => result.current.toggleDrafted("123"));
    expect(result.current.isDrafted("123")).toBe(false);
    expect(result.current.draftedCount).toBe(0);
  });

  it("tracks multiple drafted players independently", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    act(() => result.current.toggleDrafted("456"));
    expect(result.current.draftedCount).toBe(2);
    expect(result.current.isDrafted("123")).toBe(true);
    expect(result.current.isDrafted("456")).toBe(true);
    expect(result.current.isDrafted("789")).toBe(false);
  });

  it("reset clears all drafted players", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    act(() => result.current.toggleDrafted("456"));
    expect(result.current.draftedCount).toBe(2);
    act(() => result.current.reset());
    expect(result.current.draftedCount).toBe(0);
    expect(result.current.isDrafted("123")).toBe(false);
  });

  it("persists drafted ids to localStorage under the prefixed key", () => {
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    const raw = localStorage.getItem("autotiers_draft:" + KEY);
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw as string)).toEqual(["123"]);
  });

  it("round-trips: re-mounting the hook with the same key reads back persisted state", () => {
    const { result, unmount } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    act(() => result.current.toggleDrafted("456"));
    unmount();

    const { result: result2 } = renderHook(() => useDraftBoard(KEY));
    expect(result2.current.draftedCount).toBe(2);
    expect(result2.current.isDrafted("123")).toBe(true);
    expect(result2.current.isDrafted("456")).toBe(true);
  });

  it("re-seeds drafted state when storageKey changes (e.g. switching scoring format)", () => {
    localStorage.setItem("autotiers_draft:league-1:standard", JSON.stringify(["123"]));
    localStorage.setItem("autotiers_draft:league-1:ppr", JSON.stringify(["456"]));

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useDraftBoard(key),
      { initialProps: { key: "league-1:standard" } },
    );
    expect(result.current.isDrafted("123")).toBe(true);
    expect(result.current.isDrafted("456")).toBe(false);

    rerender({ key: "league-1:ppr" });
    expect(result.current.isDrafted("456")).toBe(true);
    expect(result.current.isDrafted("123")).toBe(false);
  });

  it("never writes the previous key's drafted set under the new key when storageKey changes", () => {
    localStorage.setItem("autotiers_draft:league-1:standard", JSON.stringify(["123"]));
    localStorage.setItem("autotiers_draft:league-1:ppr", JSON.stringify(["456"]));

    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");

    const { rerender } = renderHook(
      ({ key }: { key: string }) => useDraftBoard(key),
      { initialProps: { key: "league-1:standard" } },
    );

    setItemSpy.mockClear(); // ignore the initial-mount persist for "standard"
    rerender({ key: "league-1:ppr" });

    // Every write that targeted the new ("ppr") key must contain that key's own
    // data (["456"]) — the old key's data (["123"]) must never be written under
    // the new key, even transiently.
    const newKeyWrites = setItemSpy.mock.calls.filter(
      ([k]) => k === "autotiers_draft:league-1:ppr",
    );
    expect(newKeyWrites.length).toBeGreaterThan(0);
    for (const [, value] of newKeyWrites) {
      expect(JSON.parse(value as string)).toEqual(["456"]);
    }

    // And the stored value for the new key ends up correct.
    expect(JSON.parse(localStorage.getItem("autotiers_draft:league-1:ppr") as string)).toEqual(["456"]);

    setItemSpy.mockRestore();
  });

  it("does not leak drafted state between different storage keys", () => {
    const { result: a } = renderHook(() => useDraftBoard("league-a:standard"));
    act(() => a.current.toggleDrafted("123"));

    const { result: b } = renderHook(() => useDraftBoard("league-b:standard"));
    expect(b.current.isDrafted("123")).toBe(false);
    expect(b.current.draftedCount).toBe(0);
  });

  it("falls back to an empty set (does not crash) when localStorage.getItem throws", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    const { result } = renderHook(() => useDraftBoard(KEY));
    expect(result.current.draftedCount).toBe(0);
    spy.mockRestore();
  });

  it("does not crash when localStorage.setItem throws (storage-blocked fallback)", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    const { result } = renderHook(() => useDraftBoard(KEY));
    act(() => result.current.toggleDrafted("123"));
    // In-memory state still updates even though persistence failed.
    expect(result.current.isDrafted("123")).toBe(true);
    expect(result.current.draftedCount).toBe(1);
    spy.mockRestore();
  });

  it("treats malformed stored JSON as an empty set rather than crashing", () => {
    localStorage.setItem("autotiers_draft:" + KEY, "{not valid json");
    const { result } = renderHook(() => useDraftBoard(KEY));
    expect(result.current.draftedCount).toBe(0);
  });

  it("ignores non-array JSON stored under the key", () => {
    localStorage.setItem("autotiers_draft:" + KEY, JSON.stringify({ foo: "bar" }));
    const { result } = renderHook(() => useDraftBoard(KEY));
    expect(result.current.draftedCount).toBe(0);
  });

  it("filters out non-string entries from stored JSON", () => {
    localStorage.setItem("autotiers_draft:" + KEY, JSON.stringify(["123", 456, null, "789"]));
    const { result } = renderHook(() => useDraftBoard(KEY));
    expect(result.current.draftedCount).toBe(2);
    expect(result.current.isDrafted("123")).toBe(true);
    expect(result.current.isDrafted("789")).toBe(true);
  });
});
