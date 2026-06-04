import { describe, it, expect } from "vitest";
import { TIER_LABELS, getTierLabel } from "@/lib/tiers";

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
