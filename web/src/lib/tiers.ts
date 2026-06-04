export const TIER_LABELS: Readonly<Partial<Record<number, string>>> = {
  1: "Elite",
  2: "Strong Starter",
  3: "Starter",
  4: "Flex Starter",
  5: "Streamers / Deep Flex",
  6: "Handcuff / Late Round",
};

const FALLBACK_LABEL = "Late Round";

/**
 * Returns the descriptive FF vocabulary label for a given overall tier number.
 * Tiers beyond the map (7+), tier 0, and negative tiers all fall back to
 * "Late Round".
 */
export function getTierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? FALLBACK_LABEL;
}
