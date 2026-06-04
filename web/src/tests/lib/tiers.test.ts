import { describe, it, expect } from "vitest";
import { TIER_LABELS, getTierLabel, POSITIONAL_TIER_LABELS, getPositionalTierLabel } from "@/lib/tiers";

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
