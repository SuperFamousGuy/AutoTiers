import { describe, it, expect } from "vitest";
import { generateDisabledReason } from "@/lib/generateGuard";

const valid = {
  weights: { prior: 50, consensus: 50 },
  ruleCount: 3,
  profileCount: 0,
  activeProfileId: null,
} as const;

describe("generateDisabledReason", () => {
  it("returns null when every precondition is met (logged-out, no profiles)", () => {
    expect(generateDisabledReason(valid)).toBeNull();
  });

  it("returns null for a logged-in user with an active profile", () => {
    expect(
      generateDisabledReason({ ...valid, profileCount: 2, activeProfileId: "p1" }),
    ).toBeNull();
  });

  it("names the no-active-profile precondition", () => {
    expect(
      generateDisabledReason({ ...valid, profileCount: 2, activeProfileId: null }),
    ).toBe("Select or create a profile to generate.");
  });

  it("names the invalid-weights precondition", () => {
    expect(
      generateDisabledReason({ ...valid, weights: { prior: 60, consensus: 50 } }),
    ).toBe("Scoring weights must add up to 100%.");
  });

  it("names the rules-still-loading precondition", () => {
    expect(generateDisabledReason({ ...valid, ruleCount: 0 })).toBe(
      "Loading scoring rules — try again in a moment.",
    );
  });

  it("prefers the profile reason over weights and rules when all three fail", () => {
    expect(
      generateDisabledReason({
        weights: { prior: 60, consensus: 50 },
        ruleCount: 0,
        profileCount: 2,
        activeProfileId: null,
      }),
    ).toBe("Select or create a profile to generate.");
  });

  it("prefers the weights reason over rules when both fail", () => {
    expect(
      generateDisabledReason({
        weights: { prior: 60, consensus: 50 },
        ruleCount: 0,
        profileCount: 0,
        activeProfileId: null,
      }),
    ).toBe("Scoring weights must add up to 100%.");
  });
});
