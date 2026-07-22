import { useCallback, useEffect, useRef, useState } from "react";

const KEY = "autotiers.profiles.v1";
const ACTIVE_KEY = "autotiers.activeProfile.v1";

/**
 * Hard cap on locally-stored profiles. Single source of truth: App derives
 * `canCreate` from it and the profile menus render the "N/MAX" cap copy from
 * it, so the disabled "+ New Profile" affordance and the reason it shows can't
 * drift out of sync (#855).
 */
export const MAX_PROFILES = 5;

export interface LocalProfile {
  id: string;
  name: string;
  settings: Record<string, unknown>;
  rules: Record<string, unknown>;
}

function load(): LocalProfile[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LocalProfile[]) : [];
  } catch {
    return [];
  }
}

export function useLocalProfiles() {
  const [profiles, setProfiles] = useState<LocalProfile[]>(load);
  const [activeId, setActiveId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_KEY),
  );
  // Mirrors `profiles` synchronously so validation (e.g. duplicate-name
  // checks) can run BEFORE calling setState. Throwing from inside a React
  // state updater function is unreliable (React may invoke updaters more
  // than once, e.g. under StrictMode, and swallow/re-throw inconsistently),
  // so reads for validation purposes go through this ref instead.
  const profilesRef = useRef(profiles);
  profilesRef.current = profiles;

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(profiles));
  }, [profiles]);
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
    else localStorage.removeItem(ACTIVE_KEY);
  }, [activeId]);

  const create = useCallback(
    (name: string, settings: Record<string, unknown>, rules: Record<string, unknown>) => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Profile name required");
      // Enforce the hard cap here too, not just in the UI's `canCreate` gate,
      // so the invariant the docstring promises holds even if a caller reaches
      // create() without checking (#855).
      if (profilesRef.current.length >= MAX_PROFILES) {
        throw new Error("Profile limit reached");
      }
      if (profilesRef.current.some((p) => p.name === trimmed)) {
        throw new Error("Duplicate profile name");
      }
      const id = crypto.randomUUID();
      const next = [...profilesRef.current, { id, name: trimmed, settings, rules }];
      profilesRef.current = next;
      setProfiles(next);
      setActiveId(id);
      return id;
    },
    [],
  );

  const update = useCallback(
    (id: string, patch: Partial<Pick<LocalProfile, "settings" | "rules">>) =>
      setProfiles((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p))),
    [],
  );

  const rename = useCallback((id: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) throw new Error("Profile name required");
    // Reject collision with a *different* profile; renaming to the current
    // name (or same after trim) is a no-op-safe allow. Mirrors create()'s
    // duplicate guard so the two entry points can't drift.
    if (profilesRef.current.some((p) => p.id !== id && p.name === trimmed)) {
      throw new Error("Duplicate profile name");
    }
    const next = profilesRef.current.map((p) => (p.id === id ? { ...p, name: trimmed } : p));
    profilesRef.current = next;
    setProfiles(next);
  }, []);

  const remove = useCallback((id: string) => {
    setProfiles((prev) => prev.filter((p) => p.id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const activate = useCallback((id: string) => setActiveId(id), []);

  const active = profiles.find((p) => p.id === activeId) ?? null;

  return { profiles, active, create, update, rename, remove, activate };
}
