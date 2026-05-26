import { describe, it, expect } from "vitest";
import { setWeight, weightsAreValid } from "@/lib/weights";

describe("setWeight", () => {
  it("sets the chosen key without touching others", () => {
    const r = setWeight("prior", 60, { prior: 30, consensus: 70 });
    expect(r.prior).toBe(60);
    expect(r.consensus).toBe(70);
  });

  it("clamps values above 100 to 100", () => {
    const r = setWeight("prior", 150, { prior: 30, consensus: 70 });
    expect(r.prior).toBe(100);
  });

  it("clamps negative values to 0", () => {
    const r = setWeight("prior", -10, { prior: 30, consensus: 70 });
    expect(r.prior).toBe(0);
  });

  it("works for each key independently", () => {
    const base = { prior: 30, consensus: 70 };
    expect(setWeight("consensus", 50, base).consensus).toBe(50);
    expect(setWeight("prior", 25, base).prior).toBe(25);
  });
});

describe("weightsAreValid", () => {
  it("returns true when weights sum to 100", () => {
    expect(weightsAreValid({ prior: 30, consensus: 70 })).toBe(true);
  });

  it("returns false when weights don't sum to 100", () => {
    expect(weightsAreValid({ prior: 30, consensus: 71 })).toBe(false);
  });

  it("returns false when weights sum below 100", () => {
    expect(weightsAreValid({ prior: 20, consensus: 30 })).toBe(false);
  });

  it("returns true for 40/60", () => {
    expect(weightsAreValid({ prior: 40, consensus: 60 })).toBe(true);
  });
});
