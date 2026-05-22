import { describe, it, expect } from "vitest";
import { redistribute, weightsAreValid } from "@/lib/weights";

describe("redistribute", () => {
  it("keeps the sum at 100", () => {
    const result = redistribute("prior", 50, { prior: 40, consensus: 60 });
    expect(result.prior + result.consensus).toBe(100);
  });

  it("changing prior moves the delta to consensus", () => {
    const result = redistribute("prior", 70, { prior: 40, consensus: 60 });
    expect(result.prior).toBe(70);
    expect(result.consensus).toBe(30);
  });

  it("changing consensus moves the delta to prior", () => {
    const result = redistribute("consensus", 80, { prior: 40, consensus: 60 });
    expect(result.consensus).toBe(80);
    expect(result.prior).toBe(20);
  });

  it("clamps at 100 for one weight (other becomes 0)", () => {
    const result = redistribute("prior", 100, { prior: 40, consensus: 60 });
    expect(result.prior).toBe(100);
    expect(result.consensus).toBe(0);
  });

  it("integer values only", () => {
    const result = redistribute("prior", 33, { prior: 50, consensus: 50 });
    expect(Number.isInteger(result.prior)).toBe(true);
    expect(Number.isInteger(result.consensus)).toBe(true);
    expect(result.prior + result.consensus).toBe(100);
  });
});

describe("weightsAreValid", () => {
  it("returns true when weights sum to 100", () => {
    expect(weightsAreValid({ prior: 40, consensus: 60 })).toBe(true);
  });

  it("returns false when weights don't sum to 100", () => {
    expect(weightsAreValid({ prior: 40, consensus: 61 })).toBe(false);
  });
});
