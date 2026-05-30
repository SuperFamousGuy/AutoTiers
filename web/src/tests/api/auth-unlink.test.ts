import { describe, it, expect, vi, afterEach } from "vitest";
import { unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";

describe("unlink helpers", () => {
  afterEach(() => vi.restoreAllMocks());

  it("unlinkGoogle DELETEs /api/auth/google/link", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await unlinkGoogle();
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/google/link");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("unlinkYahoo DELETEs /api/auth/yahoo/link", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await unlinkYahoo();
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/yahoo/link");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("unlinkGoogle throws ApiError on non-2xx", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("Cannot unlink last sign-in method", { status: 400 }),
    );
    await expect(unlinkGoogle()).rejects.toBeInstanceOf(ApiError);
  });
});
