import { describe, it, expect } from "vitest";
import { redistribute, weightsAreValid } from "@/lib/weights";

describe("redistribute", () => {
  it("keeps the sum at 100 when balanced", () => {
    const result = redistribute("prior", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });

  it("distributes the delta proportionally when others are balanced", () => {
    const result = redistribute("prior", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.prior).toBe(50);
    expect(result.espn).toBe(25);
    expect(result.consensus).toBe(25);
  });

  it("distributes proportionally when others are unbalanced", () => {
    const result = redistribute("prior", 40, { prior: 20, espn: 60, consensus: 20 });
    expect(result.prior).toBe(40);
    expect(result.espn).toBe(45);
    expect(result.consensus).toBe(15);
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });

  it("splits evenly when both others are zero", () => {
    const result = redistribute("prior", 80, { prior: 100, espn: 0, consensus: 0 });
    expect(result.prior).toBe(80);
    expect(result.espn + result.consensus).toBe(20);
    expect(Math.abs(result.espn - result.consensus)).toBeLessThanOrEqual(1);
  });

  it("changing espn redistributes prior + consensus", () => {
    const result = redistribute("espn", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.espn).toBe(50);
    expect(result.prior + result.consensus).toBe(50);
  });

  it("changing consensus redistributes prior + espn", () => {
    const result = redistribute("consensus", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.consensus).toBe(50);
    expect(result.prior + result.espn).toBe(50);
  });

  it("clamps to integer values (no floating-point drift)", () => {
    const result = redistribute("prior", 33, { prior: 50, espn: 25, consensus: 25 });
    expect(Number.isInteger(result.prior)).toBe(true);
    expect(Number.isInteger(result.espn)).toBe(true);
    expect(Number.isInteger(result.consensus)).toBe(true);
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });
});

describe("weightsAreValid", () => {
  it("returns true when weights sum to 100", () => {
    expect(weightsAreValid({ prior: 40, espn: 30, consensus: 30 })).toBe(true);
  });

  it("returns false when weights don't sum to 100", () => {
    expect(weightsAreValid({ prior: 40, espn: 30, consensus: 31 })).toBe(false);
  });
});
