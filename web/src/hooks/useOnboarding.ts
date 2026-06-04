import { useState, useCallback } from "react";

const STORAGE_KEY = "onboarding_seen";

// True when the user has already dismissed the first-run guidance. Reads from
// localStorage so the nudge never reappears on later visits. Mirrors the
// graceful-degradation pattern in useDarkMode: if storage is blocked we treat
// the user as a first-timer (show once) rather than crashing.
function hasSeenOnboarding(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    // storage blocked — behave as if not seen, so first-run guidance still shows
    return false;
  }
}

/**
 * First-run guidance visibility.
 *
 * Returns:
 *  - showOnboarding: whether the welcome card should render right now.
 *  - dismiss: hide the card and persist that the user has seen it (never
 *    auto-shows again).
 *  - reopen: re-show the card on demand (e.g. from a Help button). Does not
 *    clear the persisted "seen" flag — reopening is a transient action.
 */
export function useOnboarding() {
  // Seeded from storage: a returning user starts with the card hidden.
  const [showOnboarding, setShow] = useState<boolean>(() => !hasSeenOnboarding());

  const dismiss = useCallback(() => {
    setShow(false);
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // storage blocked — preference not persisted; card stays dismissed for
      // this session only.
    }
  }, []);

  const reopen = useCallback(() => {
    setShow(true);
  }, []);

  return { showOnboarding, dismiss, reopen } as const;
}
