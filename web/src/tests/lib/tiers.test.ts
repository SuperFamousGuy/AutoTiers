import { describe, it, expect } from "vitest";
import { TIER_LABELS, getTierLabel, getCustomTierLabel, POSITIONAL_TIER_LABELS, getPositionalTierLabel, buildResolvedTierNames } from "@/lib/tiers";

describe("TIER_LABELS", () => {
  it("exports a record with exactly 11 entries (tiers 1-11)", () => {
    expect(Object.keys(TIER_LABELS)).toHaveLength(11);
  });

  it("contains keys 1 through 11", () => {
    for (let i = 1; i <= 11; i++) {
      expect(TIER_LABELS[i]).toBeDefined();
    }
  });

  it("maps tier 1 to Elite", () => {
    expect(TIER_LABELS[1]).toBe("Elite");
  });

  it("maps tier 6 to Handcuff / Late Round", () => {
    expect(TIER_LABELS[6]).toBe("Handcuff / Late Round");
  });

  it("maps tier 7 to Deep Sleepers", () => {
    expect(TIER_LABELS[7]).toBe("Deep Sleepers");
  });

  it("maps tier 8 to Lottery Tickets", () => {
    expect(TIER_LABELS[8]).toBe("Lottery Tickets");
  });

  it("maps tier 9 to IR Stash", () => {
    expect(TIER_LABELS[9]).toBe("IR Stash");
  });

  it("maps tier 10 to Waiver Wire", () => {
    expect(TIER_LABELS[10]).toBe("Waiver Wire");
  });

  it("maps tier 11 to Practice Squad", () => {
    expect(TIER_LABELS[11]).toBe("Practice Squad");
  });
});

describe("getTierLabel", () => {
  it.each([
    [1, "Elite"],
    [2, "Strong Starter"],
    [3, "Starter"],
    [4, "Flex Starter"],
    [5, "Streamers / Deep Flex"],
    [6, "Handcuff / Late Round"],
    [7, "Deep Sleepers"],
    [8, "Lottery Tickets"],
    [9, "IR Stash"],
    [10, "Waiver Wire"],
    [11, "Practice Squad"],
  ])("tier %i returns %s", (tier, expected) => {
    expect(getTierLabel(tier)).toBe(expected);
  });

  it("tier 12 falls back to Late Round", () => {
    expect(getTierLabel(12)).toBe("Late Round");
  });

  it("tier 0 falls back to Late Round", () => {
    expect(getTierLabel(0)).toBe("Late Round");
  });

  it("negative tier falls back to Late Round", () => {
    expect(getTierLabel(-1)).toBe("Late Round");
  });
});

describe("POSITIONAL_TIER_LABELS", () => {
  it("has entries for QB, WR, and TE", () => {
    expect(Object.keys(POSITIONAL_TIER_LABELS)).toEqual(expect.arrayContaining(["QB", "WR", "TE"]));
  });

  it("QB tier 1 maps to 'Elite QB'", () => {
    expect(POSITIONAL_TIER_LABELS["QB"]?.[1]).toBe("Elite QB");
  });

  it("WR tier 4 maps to 'Flex WR'", () => {
    expect(POSITIONAL_TIER_LABELS["WR"]?.[4]).toBe("Flex WR");
  });

  it("TE tier 1 maps to 'Elite TE'", () => {
    expect(POSITIONAL_TIER_LABELS["TE"]?.[1]).toBe("Elite TE");
  });

  it("has no entries for RB, K, or DST", () => {
    expect(POSITIONAL_TIER_LABELS["RB"]).toBeUndefined();
    expect(POSITIONAL_TIER_LABELS["K"]).toBeUndefined();
    expect(POSITIONAL_TIER_LABELS["DST"]).toBeUndefined();
  });
});

describe("getCustomTierLabel", () => {
  it("returns the static default when no overrides provided", () => {
    expect(getCustomTierLabel(1)).toBe("Elite");
  });

  it("returns the static default when overrides is undefined", () => {
    expect(getCustomTierLabel(2, undefined)).toBe("Strong Starter");
  });

  it("returns the static default when overrides does not contain the tier", () => {
    expect(getCustomTierLabel(1, { 2: "Custom" })).toBe("Elite");
  });

  it("returns the override when present for the given tier", () => {
    expect(getCustomTierLabel(1, { 1: "Studs" })).toBe("Studs");
  });

  it("returns override for tier 7 even though there is no static entry", () => {
    expect(getCustomTierLabel(7, { 7: "Deep Sleepers" })).toBe("Deep Sleepers");
  });

  it("returns the static default for tier 7 with no override", () => {
    expect(getCustomTierLabel(7)).toBe("Deep Sleepers");
  });

  it("returns the static default for tier 7 when override map is present but does not cover tier 7", () => {
    expect(getCustomTierLabel(7, { 1: "Studs" })).toBe("Deep Sleepers");
  });

  it("falls back to 'Late Round' for tier 12 with no override", () => {
    expect(getCustomTierLabel(12)).toBe("Late Round");
  });

  it("falls back to static default when override is empty string (in-progress cleared input)", () => {
    expect(getCustomTierLabel(1, { 1: "" })).toBe("Elite");
  });

  it("falls back to static default when override is whitespace-only", () => {
    expect(getCustomTierLabel(1, { 1: "   " })).toBe("Elite");
  });
});

describe("getPositionalTierLabel", () => {
  it("QB1 returns 'Elite QB'", () => {
    expect(getPositionalTierLabel("QB1")).toBe("Elite QB");
  });

  it("WR4 returns 'Flex WR'", () => {
    expect(getPositionalTierLabel("WR4")).toBe("Flex WR");
  });

  it("TE1 returns 'Elite TE'", () => {
    expect(getPositionalTierLabel("TE1")).toBe("Elite TE");
  });

  it("WR1 returns undefined (no entry for WR tier 1)", () => {
    expect(getPositionalTierLabel("WR1")).toBeUndefined();
  });

  it("WR2 returns undefined", () => {
    expect(getPositionalTierLabel("WR2")).toBeUndefined();
  });

  it("RB1 returns undefined (no entries for RB)", () => {
    expect(getPositionalTierLabel("RB1")).toBeUndefined();
  });

  it("K1 returns undefined (no entries for K)", () => {
    expect(getPositionalTierLabel("K1")).toBeUndefined();
  });

  it("DST1 returns undefined (no entries for DST)", () => {
    expect(getPositionalTierLabel("DST1")).toBeUndefined();
  });

  it("empty string returns undefined", () => {
    expect(getPositionalTierLabel("")).toBeUndefined();
  });

  it("string with no digit suffix returns undefined", () => {
    expect(getPositionalTierLabel("invalid")).toBeUndefined();
  });
});

describe("buildResolvedTierNames", () => {
  it("returns all defaults when overrides is undefined", () => {
    const result = buildResolvedTierNames(6, undefined);
    expect(result).toEqual({
      1: "Elite",
      2: "Strong Starter",
      3: "Starter",
      4: "Flex Starter",
      5: "Streamers / Deep Flex",
      6: "Handcuff / Late Round",
    });
  });

  it("returns all defaults when overrides is empty", () => {
    const result = buildResolvedTierNames(3, {});
    expect(result).toEqual({
      1: "Elite",
      2: "Strong Starter",
      3: "Starter",
    });
  });

  it("overrides replace defaults at the specified tier", () => {
    const result = buildResolvedTierNames(3, { 1: "Studs", 2: "Solid" });
    expect(result[1]).toBe("Studs");
    expect(result[2]).toBe("Solid");
    expect(result[3]).toBe("Starter");
  });

  it("includes tier entries for tiers 7-11 with their named defaults", () => {
    const result = buildResolvedTierNames(11, undefined);
    expect(result[7]).toBe("Deep Sleepers");
    expect(result[8]).toBe("Lottery Tickets");
    expect(result[9]).toBe("IR Stash");
    expect(result[10]).toBe("Waiver Wire");
    expect(result[11]).toBe("Practice Squad");
  });

  it("tier 12+ gets Late Round fallback label", () => {
    const result = buildResolvedTierNames(15, undefined);
    expect(result[12]).toBe("Late Round");
    expect(result[15]).toBe("Late Round");
  });

  it("count = 1 returns only tier 1", () => {
    const result = buildResolvedTierNames(1, undefined);
    expect(Object.keys(result)).toHaveLength(1);
    expect(result[1]).toBe("Elite");
  });

  it("count = 20 returns 20 entries including overrides", () => {
    const result = buildResolvedTierNames(20, { 15: "Custom Fifteen" });
    expect(Object.keys(result)).toHaveLength(20);
    expect(result[15]).toBe("Custom Fifteen");
    expect(result[20]).toBe("Late Round");
  });

  it("whitespace-only override is treated as empty and falls back to default", () => {
    const result = buildResolvedTierNames(3, { 1: "   " });
    // getCustomTierLabel treats whitespace-only as empty -> falls back to default
    expect(result[1]).toBe("Elite");
  });
});
