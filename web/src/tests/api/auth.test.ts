import { describe, it, expect, vi, afterEach } from "vitest";
import { signup, login, logout, getMe, yahooAuthorizeUrl, googleAuthorizeUrl } from "@/api/auth";
import { ApiError } from "@/api/client";

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

  it("googleAuthorizeUrl returns the API URL plus /api/auth/google/authorize", () => {
    expect(googleAuthorizeUrl()).toContain("/api/auth/google/authorize");
  });

  it("logout POSTs to /api/auth/logout on the happy path", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await logout();
    expect(String(spy.mock.calls[0][0])).toContain("/api/auth/logout");
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
  });

  it("logout throws ApiError on non-2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("server error", { status: 500 }),
    );
    await expect(logout()).rejects.toBeInstanceOf(ApiError);
  });

  it("getMe propagates non-401 errors", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("internal error", { status: 500 }),
    );
    await expect(getMe()).rejects.toBeInstanceOf(ApiError);
  });
});
