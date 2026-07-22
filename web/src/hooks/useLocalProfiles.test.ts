import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
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

  describe("insecure context (crypto.randomUUID undefined) — #859", () => {
    let restore: (() => void) | null = null;

    afterEach(() => {
      restore?.();
      restore = null;
    });

    function stubRandomUUIDUndefined() {
      const desc = Object.getOwnPropertyDescriptor(crypto, "randomUUID");
      Object.defineProperty(crypto, "randomUUID", {
        value: undefined,
        configurable: true,
        writable: true,
      });
      restore = () => {
        if (desc) Object.defineProperty(crypto, "randomUUID", desc);
        else delete (crypto as unknown as Record<string, unknown>).randomUUID;
      };
    }

    it("create() returns a usable, unique id instead of throwing", () => {
      stubRandomUUIDUndefined();
      const { result } = renderHook(() => useLocalProfiles());

      let firstId = "";
      let secondId = "";
      expect(() =>
        act(() => {
          firstId = result.current.create("A", {}, {});
        }),
      ).not.toThrow();
      act(() => {
        secondId = result.current.create("B", {}, {});
      });

      // Non-empty, distinct, and actually the ids stored on the profiles.
      expect(firstId).toBeTruthy();
      expect(secondId).toBeTruthy();
      expect(firstId).not.toBe(secondId);
      expect(result.current.profiles.map((p) => p.id)).toEqual([firstId, secondId]);
      expect(result.current.active?.id).toBe(secondId);
    });
  });

  it("rejects renaming onto another profile's name but allows a self-rename", () => {
    const { result } = renderHook(() => useLocalProfiles());
    let aId = "";
    act(() => { aId = result.current.create("A", {}, {}); });
    act(() => { result.current.create("B", {}, {}); });

    // A -> "B" collides with the other profile: rejected.
    expect(() => act(() => result.current.rename(aId, "B"))).toThrow();
    expect(result.current.profiles.find((p) => p.id === aId)?.name).toBe("A");

    // Renaming A to its own current name is allowed (no-op-safe).
    expect(() => act(() => result.current.rename(aId, "A"))).not.toThrow();
  });
});
