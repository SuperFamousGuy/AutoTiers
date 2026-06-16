import { describe, it, expect } from "vitest";
import { POSITIONS, POSITION_RULES_MAP } from "@/lib/positionRulesMap";

describe("positionRulesMap", () => {
  it("POSITIONS contains all 6 positions in order", () => {
    expect(POSITIONS).toEqual(["QB", "RB", "WR", "TE", "K", "DST"]);
  });

  it("POSITION_RULES_MAP has an entry for every position", () => {
    for (const pos of POSITIONS) {
      expect(POSITION_RULES_MAP[pos]).toBeDefined();
      expect(POSITION_RULES_MAP[pos].length).toBeGreaterThan(0);
    }
  });

  it("RB tab has the most rules (17)", () => {
    expect(POSITION_RULES_MAP["RB"].length).toBe(17);
  });

  it("K tab has exactly 7 rules incl. the three kicker-specific rules", () => {
    expect(POSITION_RULES_MAP["K"].length).toBe(7);
    expect(POSITION_RULES_MAP["K"]).toContain("Projection Unavailable");
    expect(POSITION_RULES_MAP["K"]).toContain("Year After the Year After");
    expect(POSITION_RULES_MAP["K"]).toContain("Over the Hill");
    expect(POSITION_RULES_MAP["K"]).toContain("Favorites");
    // The three kicker-specific builtin rules (backend positions=["K"]).
    expect(POSITION_RULES_MAP["K"]).toContain("Dome Kicker");
    expect(POSITION_RULES_MAP["K"]).toContain("Mile High Kicker");
    expect(POSITION_RULES_MAP["K"]).toContain("Cold-Weather Kicker");
  });

  it("DST tab has exactly 2 rules", () => {
    expect(POSITION_RULES_MAP["DST"].length).toBe(2);
    expect(POSITION_RULES_MAP["DST"]).toContain("Projection Unavailable");
    expect(POSITION_RULES_MAP["DST"]).toContain("Favorites");
  });

  it("Target Share Premium appears in RB, WR, TE but not QB, K, DST", () => {
    expect(POSITION_RULES_MAP["RB"]).toContain("Target Share Premium");
    expect(POSITION_RULES_MAP["WR"]).toContain("Target Share Premium");
    expect(POSITION_RULES_MAP["TE"]).toContain("Target Share Premium");
    expect(POSITION_RULES_MAP["QB"]).not.toContain("Target Share Premium");
    expect(POSITION_RULES_MAP["K"]).not.toContain("Target Share Premium");
    expect(POSITION_RULES_MAP["DST"]).not.toContain("Target Share Premium");
  });

  it("Favorites appears in all 6 positions", () => {
    for (const pos of POSITIONS) {
      expect(POSITION_RULES_MAP[pos]).toContain("Favorites");
    }
  });

  it("370 Touches does not appear in any position tab (hidden by design)", () => {
    for (const pos of POSITIONS) {
      expect(POSITION_RULES_MAP[pos]).not.toContain("370 Touches");
    }
  });

  it("Declining Snap% appears in RB, WR, TE but not QB, K, DST", () => {
    expect(POSITION_RULES_MAP["RB"]).toContain("Declining Snap%");
    expect(POSITION_RULES_MAP["WR"]).toContain("Declining Snap%");
    expect(POSITION_RULES_MAP["TE"]).toContain("Declining Snap%");
    expect(POSITION_RULES_MAP["QB"]).not.toContain("Declining Snap%");
    expect(POSITION_RULES_MAP["K"]).not.toContain("Declining Snap%");
    expect(POSITION_RULES_MAP["DST"]).not.toContain("Declining Snap%");
  });
});
