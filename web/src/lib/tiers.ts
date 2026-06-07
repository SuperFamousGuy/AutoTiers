export const TIER_LABELS: Readonly<Partial<Record<number, string>>> = {
  1: "Elite",
  2: "Strong Starter",
  3: "Starter",
  4: "Flex Starter",
  5: "Streamers / Deep Flex",
  6: "Handcuff / Late Round",
  7: "Deep Sleepers",
  8: "Lottery Tickets",
  9: "IR Stash",
  10: "Waiver Wire",
  11: "Practice Squad",
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
 * Returns the descriptive label for a given overall tier, using the user-supplied
 * override when present, and falling back to the static default (including the
 * "Late Round" fallback for tier 7+).
 */
export function getCustomTierLabel(
  tier: number,
  overrides?: Partial<Record<number, string>>,
): string {
  const override = overrides?.[tier];
  if (override !== undefined && override.trim() !== "") return override;
  return getTierLabel(tier);
}

/**
 * Builds a fully-resolved map of tier labels for all tiers 1..tierCount.
 * Applies user overrides where present; defaults to the static TIER_LABELS
 * (including the extended entries for tiers 7-11) and falls back to "Late Round"
 * for tiers 12+. The result is a dense map — every key 1..tierCount is present.
 *
 * This is a pure function safe to call on every render; the loop runs at most
 * 25 iterations (UI caps tier count at 25).
 */
export function buildResolvedTierNames(
  tierCount: number,
  overrides: Partial<Record<number, string>> | undefined,
): Record<number, string> {
  const result: Record<number, string> = {};
  for (let t = 1; t <= tierCount; t++) {
    result[t] = getCustomTierLabel(t, overrides);
  }
  return result;
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
