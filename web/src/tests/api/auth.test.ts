import { describe, it, expect, vi, afterEach } from "vitest";
import { signup, login, getMe, yahooAuthorizeUrl } from "@/api/auth";

describe("auth API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("signup POSTs to /api/auth/signup and returns MeResponse", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] }), { status: 201 }),
    );
    const result = await signup({ email: "a@b.com", password: "longenough123" });
    expect(result.user.email).toBe("a@b.com");
  });

  it("login POSTs to /api/auth/login", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ user: { id: "u1", email: "a@b.com", yahoo_subject: null, last_active_profile_id: null }, profiles: [] }), { status: 200 }),
    );
    await login({ email: "a@b.com", password: "x" });
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/login");
  });

  it("getMe returns null on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    const result = await getMe();
    expect(result).toBeNull();
  });

  it("yahooAuthorizeUrl returns the API URL plus /api/auth/yahoo/authorize", () => {
    expect(yahooAuthorizeUrl()).toContain("/api/auth/yahoo/authorize");
  });
});
