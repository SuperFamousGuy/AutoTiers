import { useState, useCallback } from "react";

const STORAGE_KEY = "onboarding_seen";

// True when the user has already completed/dismissed the first-run guidance.
// Reads from localStorage so the tour never auto-starts on later visits. Mirrors
// the graceful-degradation pattern in useDarkMode: if storage is blocked we treat
// the user as a first-timer (auto-starts on every visit) rather than crashing.
function hasSeenOnboarding(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    // storage blocked — behave as if not seen, so first-run guidance still shows
    return false;
  }
}

function persistSeen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // storage blocked — preference not persisted; tour stays closed for this
    // session only.
  }
}

/**
 * Interactive onboarding tour state — a small step machine.
 *
 * Returns:
 *  - active: whether the tour overlay should render right now.
 *  - stepIndex: zero-based index of the current step.
 *  - start: open the tour at step 0. Used both for the first-run auto-show and
 *    for the Help/replay control. Does NOT clear the persisted "seen" flag —
 *    replaying is a transient action.
 *  - next / back: move between steps. `next` past the last step finishes.
 *  - goTo: jump to a specific step (e.g. clicking a progress dot).
 *  - skip: close the tour early AND persist "seen" (the user opted out — don't
 *    nag them again next visit).
 *  - finish: close the tour after the last step AND persist "seen".
 *
 * @param totalSteps number of steps in the tour. Bounds navigation.
 */
export function useOnboarding(totalSteps: number) {
  // Seeded from storage: a returning user starts with the tour closed.
  const [active, setActive] = useState<boolean>(() => !hasSeenOnboarding());
  const [stepIndex, setStepIndex] = useState(0);

  const start = useCallback(() => {
    setStepIndex(0);
    setActive(true);
  }, []);

  const skip = useCallback(() => {
    setActive(false);
    persistSeen();
  }, []);

  const finish = useCallback(() => {
    setActive(false);
    persistSeen();
  }, []);

  const next = useCallback(() => {
    setStepIndex((i) => {
      if (i >= totalSteps - 1) {
        // Past the last step — finish the tour and persist.
        setActive(false);
        persistSeen();
        return i;
      }
      return i + 1;
    });
  }, [totalSteps]);

  const back = useCallback(() => {
    setStepIndex((i) => (i > 0 ? i - 1 : 0));
  }, []);

  const goTo = useCallback((i: number) => {
    setStepIndex(() => {
      if (i < 0) return 0;
      if (i > totalSteps - 1) return totalSteps - 1;
      return i;
    });
  }, [totalSteps]);

  return { active, stepIndex, totalSteps, start, next, back, goTo, skip, finish } as const;
}
