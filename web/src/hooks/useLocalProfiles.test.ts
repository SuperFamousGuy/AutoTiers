import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useLocalProfiles } from "./useLocalProfiles";

beforeEach(() => localStorage.clear());

describe("useLocalProfiles", () => {
  it("creates, persists, and switches profiles", () => {
    const { result } = renderHook(() => useLocalProfiles());
    act(() => result.current.create("PPR", { scoring: "ppr" }, {}));
    expect(result.current.profiles.map((p) => p.name)).toContain("PPR");
    expect(result.current.active?.name).toBe("PPR");
    // persisted
    const raw = localStorage.getItem("autotiers.profiles.v1");
    expect(raw).toContain("PPR");
  });

  it("renames and deletes", () => {
    const { result } = renderHook(() => useLocalProfiles());
    let id = "";
    act(() => { id = result.current.create("A", {}, {}); });
    act(() => result.current.rename(id, "B"));
    expect(result.current.profiles[0].name).toBe("B");
    act(() => result.current.remove(id));
    expect(result.current.profiles).toHaveLength(0);
  });

  it("rejects duplicate names", () => {
    const { result } = renderHook(() => useLocalProfiles());
    act(() => result.current.create("A", {}, {}));
    expect(() => act(() => result.current.create("A", {}, {}))).toThrow();
  });
});
