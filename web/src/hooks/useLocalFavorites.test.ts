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
});
