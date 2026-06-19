import type { ScoringFormat } from "@/api/types";

/** A sparse map of tier number → custom label. Omitted tiers fall back to defaults. */
export type TierLabelOverrides = Partial<Record<number, string>>;

/**
 * Per-scoring-format tier label overrides (#164). Each scoring format may carry
 * its own sparse override map; formats absent here fall back to the global
 * `tier_labels` and then to the static defaults.
 */
export type TierLabelsByFormat = Partial<Record<ScoringFormat, TierLabelOverrides>>;

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
 * TIER_LABELS now covers tiers 1-11; tiers beyond the map (12+), tier 0, and
 * negative tiers all fall back to "Late Round".
 */
export function getTierLabel(tier: number): string {
  return TIER_LABELS[tier] ?? FALLBACK_LABEL;
}

/**
 * Returns the descriptive label for a given overall tier, using the user-supplied
 * override when present, and falling back to the static default (tiers 1-11
 * have named defaults; tier 12+ falls back to "Late Round").
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
 * Resolves the effective tier-label overrides for a given scoring format (#164).
 * The active format's per-format overrides take precedence over the global
 * `tier_labels`; tiers absent from the per-format map fall through to the global
 * value (and, downstream, to the static default). Returns a plain merged map —
 * an empty object when nothing is configured. Pure; safe to call on every render.
 */
export function resolveTierLabelOverrides(
  global: TierLabelOverrides | undefined,
  byFormat: TierLabelsByFormat | undefined,
  format: ScoringFormat,
): TierLabelOverrides {
  const formatOverrides = byFormat?.[format];
  if (!formatOverrides || Object.keys(formatOverrides).length === 0) {
    return { ...(global ?? {}) };
  }
  return { ...(global ?? {}), ...formatOverrides };
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
