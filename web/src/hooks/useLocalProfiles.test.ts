import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type LocalProfile, useLocalProfiles } from "./useLocalProfiles";

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

  it("keeps independent hook instances in sync within a session", () => {
    // Mirrors the real app: App.tsx's autosave holds one hook instance while
    // the profile switcher/manager holds another. A write through either must
    // be visible to the other without a remount (#854).
    const a = renderHook(() => useLocalProfiles());
    const b = renderHook(() => useLocalProfiles());

    let id = "";
    act(() => { id = a.result.current.create("Dynasty", { scoring: "ppr" }, {}); });

    // Instance b reflects the create — profiles AND the newly-active id.
    expect(b.result.current.profiles.map((p) => p.name)).toContain("Dynasty");
    expect(b.result.current.active?.id).toBe(id);

    // A rename through b is visible to a.
    act(() => b.result.current.rename(id, "Keeper"));
    expect(a.result.current.profiles.find((p) => p.id === id)?.name).toBe("Keeper");

    // activate() through a re-syncs b's active pointer.
    let otherId = "";
    act(() => { otherId = a.result.current.create("Redraft", {}, {}); });
    act(() => b.result.current.activate(id));
    expect(a.result.current.active?.id).toBe(id);
    expect(b.result.current.active?.id).toBe(id);
    expect(otherId).not.toBe(id);
  });

  it("does not let a stale instance's update() drop another instance's profile", () => {
    // Regression for the lost-update in #854: tab B edits Settings and its
    // debounced autosave calls update() against a React snapshot that predates
    // tab A creating a profile. Simulate that by writing a second profile
    // straight to localStorage (a write instance B never observed) and then
    // calling update() on B; the read-through must preserve it.
    const b = renderHook(() => useLocalProfiles());
    let aId = "";
    act(() => { aId = b.result.current.create("A", { v: 1 }, {}); });

    // Another tab appended "Dynasty" without notifying this instance.
    const raw = JSON.parse(localStorage.getItem("autotiers.profiles.v1")!) as unknown[];
    localStorage.setItem(
      "autotiers.profiles.v1",
      JSON.stringify([...raw, { id: "dyn", name: "Dynasty", settings: {}, rules: {} }]),
    );

    // Stale-instance autosave writes A. Read-through must keep "Dynasty".
    act(() => b.result.current.update(aId, { settings: { v: 2 } }));

    const persisted = JSON.parse(localStorage.getItem("autotiers.profiles.v1")!) as LocalProfile[];
    expect(persisted.map((p) => p.name).sort()).toEqual(["A", "Dynasty"]);
    expect(persisted.find((p) => p.id === aId)?.settings).toEqual({ v: 2 });
  });

  it("re-reads on a cross-tab storage event", () => {
    const { result } = renderHook(() => useLocalProfiles());
    // Simulate another tab's write: mutate localStorage, then fire the event
    // the browser would dispatch (jsdom does not emit it for same-context writes).
    localStorage.setItem(
      "autotiers.profiles.v1",
      JSON.stringify([{ id: "x", name: "FromOtherTab", settings: {}, rules: {} }]),
    );
    localStorage.setItem("autotiers.activeProfile.v1", "x");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "autotiers.profiles.v1" }));
      window.dispatchEvent(new StorageEvent("storage", { key: "autotiers.activeProfile.v1" }));
    });
    expect(result.current.profiles.map((p) => p.name)).toEqual(["FromOtherTab"]);
    expect(result.current.active?.id).toBe("x");
  });
});
