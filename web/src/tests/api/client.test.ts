import { describe, it, expect, vi, afterEach } from "vitest";
import { ApiError, apiFetch } from "@/api/client";

describe("ApiError", () => {
  it("preserves status and sets name", () => {
    const err = new ApiError(404, "not found");
    expect(err.status).toBe(404);
    expect(err.message).toBe("not found");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed JSON on a 2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, count: 3 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiFetch<{ ok: boolean; count: number }>("/api/test");

    expect(result).toEqual({ ok: true, count: 3 });
  });

  it("throws ApiError with body text on non-2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("rule validation failed", { status: 422 }),
    );

    await expect(apiFetch("/api/generate")).rejects.toMatchObject({
      status: 422,
      message: "rule validation failed",
      name: "ApiError",
    });
  });

  it("falls back to statusText when body is empty", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("", { status: 500, statusText: "Internal Server Error" }),
    );

    await expect(apiFetch("/api/whatever")).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });
});
