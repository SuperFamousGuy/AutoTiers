import { describe, it, expect } from "vitest";
import { redistribute, weightsAreValid } from "@/lib/weights";

describe("redistribute", () => {
  it("keeps the sum at 100 when balanced", () => {
    const r = redistribute("prior", 50, { prior: 30, consensus: 40, adp: 30 });
    expect(r.prior + r.consensus + r.adp).toBe(100);
  });

  it("distributes proportionally between the other two", () => {
    // others initially 40/30 (4:3 ratio). prior goes 30 → 60, others lose 30 total.
    const r = redistribute("prior", 60, { prior: 30, consensus: 40, adp: 30 });
    expect(r.prior).toBe(60);
    expect(r.prior + r.consensus + r.adp).toBe(100);
  });

  it("changing consensus redistributes prior + adp", () => {
    const r = redistribute("consensus", 60, { prior: 30, consensus: 40, adp: 30 });
    expect(r.consensus).toBe(60);
    expect(r.prior + r.adp).toBe(40);
  });

  it("changing adp redistributes prior + consensus", () => {
    const r = redistribute("adp", 60, { prior: 30, consensus: 40, adp: 30 });
    expect(r.adp).toBe(60);
    expect(r.prior + r.consensus).toBe(40);
  });

  it("splits evenly when both others are zero", () => {
    const r = redistribute("prior", 80, { prior: 100, consensus: 0, adp: 0 });
    expect(r.prior).toBe(80);
    expect(r.consensus + r.adp).toBe(20);
    expect(Math.abs(r.consensus - r.adp)).toBeLessThanOrEqual(1);
  });

  it("integer values only", () => {
    const r = redistribute("prior", 33, { prior: 40, consensus: 30, adp: 30 });
    expect(Number.isInteger(r.prior)).toBe(true);
    expect(Number.isInteger(r.consensus)).toBe(true);
    expect(Number.isInteger(r.adp)).toBe(true);
    expect(r.prior + r.consensus + r.adp).toBe(100);
  });
});

describe("weightsAreValid", () => {
  it("returns true when weights sum to 100", () => {
    expect(weightsAreValid({ prior: 30, consensus: 40, adp: 30 })).toBe(true);
  });

  it("returns false when weights don't sum to 100", () => {
    expect(weightsAreValid({ prior: 30, consensus: 40, adp: 31 })).toBe(false);
  });
});
