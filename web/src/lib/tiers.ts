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

/**
 * Descriptive labels for notable positional tiers only. Positions and tiers
 * that are self-explanatory (RB, K, DST) have no entries.
 */
export const POSITIONAL_TIER_LABELS: Readonly<
  Partial<Record<string, Readonly<Partial<Record<number, string>>>>>
> = {
  QB: { 1: "Elite QB" },
  WR: { 4: "Flex WR" },
  TE: { 1: "Elite TE" },
};

/**
 * Returns the descriptive label for a positional tier string such as "QB1" or
 * "WR4", or undefined if no notable label exists for that tier.
 */
export function getPositionalTierLabel(positionalTierStr: string): string | undefined {
  const match = positionalTierStr.match(/^([A-Za-z]+)(\d+)$/);
  if (!match) return undefined;
  const position = match[1];
  const tierNum = parseInt(match[2], 10);
  return POSITIONAL_TIER_LABELS[position]?.[tierNum];
}
