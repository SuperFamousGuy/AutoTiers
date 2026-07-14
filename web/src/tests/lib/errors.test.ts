import { describe, it, expect } from "vitest";
import { describeGenerateError, describeSaveError } from "@/lib/errors";
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

  it("unwraps a Pydantic 4xx validation body (no raw JSON reaches the user)", () => {
    // The real shape apiFetch stores for a generate weight-sum rejection:
    // FastAPI/Pydantic returns {"detail": [{loc, msg, type}]}.
    const body = JSON.stringify({
      detail: [
        {
          loc: ["body", "weight_consensus"],
          msg: "Value error, Score weights must sum to 1.0, got 1.20",
          type: "value_error",
        },
      ],
    });
    const msg = describeGenerateError(new ApiError(422, body));
    expect(msg).toBe("Value error, Score weights must sum to 1.0, got 1.20");
    // The JSON envelope must not leak through.
    expect(msg).not.toMatch(/[{}[\]]|detail/);
  });

  it("joins multiple Pydantic validation messages", () => {
    const body = JSON.stringify({
      detail: [
        { loc: ["body", "league_size"], msg: "league_size must be one of: 8, 10, 12, 14, 16" },
        { loc: ["body", "draft_rounds"], msg: "draft_rounds must be between 1 and 30" },
      ],
    });
    const msg = describeGenerateError(new ApiError(422, body));
    expect(msg).toBe(
      "league_size must be one of: 8, 10, 12, 14, 16 draft_rounds must be between 1 and 30",
    );
  });

  it("unwraps a string HTTPException detail", () => {
    const body = JSON.stringify({ detail: "No projection data available yet." });
    expect(describeGenerateError(new ApiError(400, body))).toBe(
      "No projection data available yet.",
    );
  });

  it("passes a non-JSON 4xx body through unchanged", () => {
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

describe("describeSaveError", () => {
  it("names the client timeout", () => {
    expect(describeSaveError(new TimeoutError(30_000))).toMatch(/timed out/i);
  });

  it("gives a save-flavoured, blame-free line for a 5xx (hides the raw body)", () => {
    const msg = describeSaveError(new ApiError(500, "<html>Internal Server Error</html>"));
    expect(msg).toMatch(/couldn't save|could not save/i);
    // Unlike describeGenerateError, the copy must not mention building tiers.
    expect(msg).not.toMatch(/tiers/i);
    expect(msg).not.toMatch(/<html>/);
  });

  it("unwraps a string HTTPException detail for a 4xx", () => {
    const body = JSON.stringify({ detail: "Payload too large." });
    expect(describeSaveError(new ApiError(413, body))).toBe("Payload too large.");
  });

  it("falls back to the status when a 4xx has an empty body", () => {
    expect(describeSaveError(new ApiError(400, ""))).toMatch(/failed \(400\)/i);
  });

  it("surfaces a raw network TypeError's message", () => {
    expect(describeSaveError(new TypeError("Failed to fetch"))).toBe("Failed to fetch");
  });

  it("has a generic fallback for a non-Error throw", () => {
    expect(describeSaveError(null)).toMatch(/something went wrong/i);
  });
});
