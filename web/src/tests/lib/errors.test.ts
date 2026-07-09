import { describe, it, expect } from "vitest";
import { describeGenerateError } from "@/lib/errors";
import { ApiError, TimeoutError } from "@/api/client";

describe("describeGenerateError", () => {
  it("names the 30s client timeout", () => {
    expect(describeGenerateError(new TimeoutError(30_000))).toMatch(/timed out/i);
  });

  it("gives a generic, blame-free line for a 5xx (hides the raw server body)", () => {
    const msg = describeGenerateError(new ApiError(500, "<html>Internal Server Error</html>"));
    expect(msg).toMatch(/server/i);
    // The noisy raw body must not reach the user.
    expect(msg).not.toMatch(/<html>/);
  });

  it("passes a 4xx message through (weight-tolerance / validation rejections are meant to be read)", () => {
    const msg = describeGenerateError(new ApiError(422, "weights must sum to 100"));
    expect(msg).toBe("weights must sum to 100");
  });

  it("falls back to the status when a 4xx has an empty body", () => {
    expect(describeGenerateError(new ApiError(400, ""))).toMatch(/failed \(400\)/i);
  });

  it("surfaces a raw network TypeError's message (fetch rejection)", () => {
    expect(describeGenerateError(new TypeError("Failed to fetch"))).toBe("Failed to fetch");
  });

  it("has a generic fallback for a non-Error throw", () => {
    expect(describeGenerateError("boom")).toMatch(/something went wrong/i);
  });
});
