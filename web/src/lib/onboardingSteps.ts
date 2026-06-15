import type { MobilePanel } from "@/components/MobilePanelTabBar";

/**
 * One step of the interactive onboarding tour.
 *
 * - `anchor`: CSS selector for the real UI element to highlight. `null` renders
 *   the step centered (welcome / finish). Selectors target stable IDs and
 *   `data-tour` markers rather than copy, so they survive text changes.
 * - `mobilePanel`: on narrow viewports the tour switches the active panel so the
 *   highlighted element is actually on screen. Omitted for centered steps.
 */
export interface OnboardingStep {
  id: string;
  anchor: string | null;
  title: string;
  body: string;
  mobilePanel?: MobilePanel;
}

export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  {
    id: "welcome",
    anchor: null,
    title: "Welcome to AutoTiers",
    body: "Let's build your first draft tier list. This quick tour walks through the four steps — about 30 seconds.",
  },
  {
    id: "settings",
    anchor: "#panel-settings",
    title: "1. Set up your league",
    body: "AutoTiers ranks every player for your league's rules. Start here: pick your scoring format and league size so the projections match your draft.",
    mobilePanel: "settings",
  },
  {
    id: "rules",
    anchor: "#panel-rules",
    title: "2. Weight what you value",
    body: "Rules nudge players up or down — boost rushing QBs, reward target share, and so on. Tiers group players of similar value, and your rules shape that value.",
    mobilePanel: "rules",
  },
  {
    id: "generate",
    anchor: '[data-tour="generate"]',
    title: "3. Build your tiers",
    body: "Hit Generate to crunch the projections and your rules into ranked tiers. (Generate stays disabled until your score weights total 100%.)",
    mobilePanel: "settings",
  },
  {
    id: "download",
    anchor: "#panel-tiers",
    title: "4. Take it to draft day",
    body: "Your tiers appear here. Download the CSV to bring them to your draft. You can replay this tour anytime from the help (?) button.",
    mobilePanel: "tiers",
  },
] as const;
