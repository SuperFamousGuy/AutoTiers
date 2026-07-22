import { useCallback, useEffect, useState } from "react";

const KEY = "autotiers.profiles.v1";
const ACTIVE_KEY = "autotiers.activeProfile.v1";

export interface LocalProfile {
  id: string;
  name: string;
  settings: Record<string, unknown>;
  rules: Record<string, unknown>;
}

function loadProfiles(): LocalProfile[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LocalProfile[]) : [];
  } catch {
    return [];
  }
}

function loadActiveId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

// localStorage is the single source of truth. Every hook instance subscribes to
// this shared listener set, and every write re-notifies all instances to
// re-read — so two independent `useLocalProfiles()` callers (e.g. App's
// autosave and the profile switcher, or two browser tabs) never drift out of
// sync. Mirrors `useLocalFavorites.ts`; without it a second tab's stale
// autosave would clobber a profile the first tab just created (#854). As there,
// we deliberately do NOT cache the value in a module-level variable: reading
// straight from localStorage keeps test isolation intact (a test's
// `localStorage.clear()` is immediately observed by the next mount).
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((l) => l());
}

function persistProfiles(next: LocalProfile[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage full / disabled (private mode) — persistence is best-effort.
  }
  notify();
}

function persistActiveId(id: string | null): void {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    // Storage full / disabled (private mode) — persistence is best-effort.
  }
  notify();
}

export function useLocalProfiles() {
  const [profiles, setProfiles] = useState<LocalProfile[]>(loadProfiles);
  const [activeId, setActiveId] = useState<string | null>(loadActiveId);

  useEffect(() => {
    const refresh = () => {
      setProfiles(loadProfiles());
      setActiveId(loadActiveId());
    };
    listeners.add(refresh);
    // Cross-tab sync: another tab's write fires a `storage` event here.
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY || e.key === ACTIVE_KEY || e.key === null) refresh();
    };
    window.addEventListener("storage", onStorage);
    // Re-sync on mount in case another instance wrote before this one mounted.
    refresh();
    return () => {
      listeners.delete(refresh);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  // Every mutation reads current state straight from localStorage before
  // mutating, rather than trusting this instance's React snapshot — the
  // snapshot can be stale if another instance/tab wrote after this one
  // rendered. notify() then re-syncs every instance (including this one).
  const create = useCallback(
    (name: string, settings: Record<string, unknown>, rules: Record<string, unknown>) => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Profile name required");
      const current = loadProfiles();
      if (current.some((p) => p.name === trimmed)) {
        throw new Error("Duplicate profile name");
      }
      const id = crypto.randomUUID();
      persistProfiles([...current, { id, name: trimmed, settings, rules }]);
      persistActiveId(id);
      return id;
    },
    [],
  );

  const update = useCallback(
    (id: string, patch: Partial<Pick<LocalProfile, "settings" | "rules">>) => {
      const current = loadProfiles();
      persistProfiles(current.map((p) => (p.id === id ? { ...p, ...patch } : p)));
    },
    [],
  );

  const rename = useCallback((id: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) throw new Error("Profile name required");
    const current = loadProfiles();
    // Reject collision with a *different* profile; renaming to the current
    // name (or same after trim) is a no-op-safe allow. Mirrors create()'s
    // duplicate guard so the two entry points can't drift.
    if (current.some((p) => p.id !== id && p.name === trimmed)) {
      throw new Error("Duplicate profile name");
    }
    persistProfiles(current.map((p) => (p.id === id ? { ...p, name: trimmed } : p)));
  }, []);

  const remove = useCallback((id: string) => {
    persistProfiles(loadProfiles().filter((p) => p.id !== id));
    if (loadActiveId() === id) persistActiveId(null);
  }, []);

  const activate = useCallback((id: string) => persistActiveId(id), []);

  const active = profiles.find((p) => p.id === activeId) ?? null;

  return { profiles, active, create, update, rename, remove, activate };
}
