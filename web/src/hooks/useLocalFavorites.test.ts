import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocalFavorites } from "./useLocalFavorites";

beforeEach(() => localStorage.clear());

describe("useLocalFavorites", () => {
  it("toggles players and persists, capped at 20", () => {
    const { result } = renderHook(() => useLocalFavorites());
    act(() => result.current.togglePlayer("p1"));
    expect(result.current.isFavoritePlayer("p1")).toBe(true);
    act(() => result.current.togglePlayer("p1"));
    expect(result.current.isFavoritePlayer("p1")).toBe(false);
    act(() => {
      for (let i = 0; i < 25; i++) result.current.togglePlayer(`x${i}`);
    });
    expect(result.current.players.length).toBeLessThanOrEqual(20);
  });

  it("caps teams at 4", () => {
    const { result } = renderHook(() => useLocalFavorites());
    act(() => ["BUF", "KC", "SF", "DAL", "PHI"].forEach((t) => result.current.toggleTeam(t)));
    expect(result.current.teams.length).toBeLessThanOrEqual(4);
  });

  it("keeps independent hook instances in sync within a session", () => {
    // App.tsx itself uses a single useLocalFavorites instance for both the
    // tier-list star badges and the Favorites swimlane, but the hook must still
    // keep any two live instances in the same session in sync — this exercises
    // that cross-instance broadcast directly.
    const reader = renderHook(() => useLocalFavorites());
    const toggler = renderHook(() => useLocalFavorites());

    act(() => toggler.result.current.togglePlayer("p1"));
    expect(reader.result.current.isFavoritePlayer("p1")).toBe(true);

    act(() => toggler.result.current.toggleTeam("KC"));
    expect(reader.result.current.isFavoriteTeam("KC")).toBe(true);

    act(() => toggler.result.current.togglePlayer("p1"));
    expect(reader.result.current.isFavoritePlayer("p1")).toBe(false);
  });
});
