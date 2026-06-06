import { describe, it, expect } from "vitest";
import { TIER_LABELS, getTierLabel, getCustomTierLabel, POSITIONAL_TIER_LABELS, getPositionalTierLabel } from "@/lib/tiers";

describe("TIER_LABELS", () => {
  it("exports a record with exactly 6 entries", () => {
    expect(Object.keys(TIER_LABELS)).toHaveLength(6);
  });

  it("maps tier 1 to Elite", () => {
    expect(TIER_LABELS[1]).toBe("Elite");
  });

  it("maps tier 6 to Handcuff / Late Round", () => {
    expect(TIER_LABELS[6]).toBe("Handcuff / Late Round");
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
  ])("tier %i returns %s", (tier, expected) => {
    expect(getTierLabel(tier)).toBe(expected);
  });

  it("tier 7 falls back to Late Round", () => {
    expect(getTierLabel(7)).toBe("Late Round");
  });

  it("tier 8 falls back to Late Round", () => {
    expect(getTierLabel(8)).toBe("Late Round");
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

  it("falls back to 'Late Round' for tier 7 with no override", () => {
    expect(getCustomTierLabel(7)).toBe("Late Round");
  });

  it("falls back to 'Late Round' for tier 7 when override map is present but does not cover tier 7", () => {
    expect(getCustomTierLabel(7, { 1: "Studs" })).toBe("Late Round");
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
