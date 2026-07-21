import { weightsAreValid, type Weights } from "@/lib/weights";

export interface GenerateGuardState {
  weights: Weights;
  /** Number of scoring rules loaded from the backend (0 while still loading). */
  ruleCount: number;
  /** Profiles the logged-in user owns; empty for logged-out users. */
  profileCount: number;
  /** The active profile id, or null when none is selected. */
  activeProfileId: string | null;
}

/**
 * Why the Generate button is disabled, or null when every precondition is met.
 *
 * Priority when several fail at once: profile > weights > rules (#838). The
 * profile gate is the one a user can act on immediately, invalid weights are
 * next, and rules-loading is transient — so the higher-priority, more
 * actionable reason wins. A null return is exactly the enabled state.
 */
export function generateDisabledReason(state: GenerateGuardState): string | null {
  const { weights, ruleCount, profileCount, activeProfileId } = state;
  if (profileCount > 0 && activeProfileId === null) {
    return "Select or create a profile to generate.";
  }
  if (!weightsAreValid(weights)) {
    return "Scoring weights must add up to 100%.";
  }
  if (ruleCount === 0) {
    return "Loading scoring rules — try again in a moment.";
  }
  return null;
}
