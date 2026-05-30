import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { ReactNode } from "react";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";

const me = { user: { id: "u1", email: "a@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: null }, profiles: [] };

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe("AuthContext", () => {
  it("starts in loading state, then settles to anonymous on 401", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response("", { status: 401 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
    vi.restoreAllMocks();
  });

  it("settles to authenticated when /me returns user", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user?.email).toBe("a@b.com");
    vi.restoreAllMocks();
  });

  it("signup populates user and profiles from response", async () => {
    const fetchSpy = vi.spyOn(global, "fetch")
      // /me on mount
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      // signup
      .mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 201 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.signup({ email: "a@b.com", password: "longenough123" });
    });
    expect(result.current.user?.email).toBe("a@b.com");
    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
    vi.restoreAllMocks();
  });

  it("login populates user and profiles from response", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.login({ email: "a@b.com", password: "x" });
    });
    expect(result.current.user?.email).toBe("a@b.com");
    vi.restoreAllMocks();
  });

  it("logout clears user and profiles", async () => {
    vi.spyOn(global, "fetch")
      // /me on mount returns user
      .mockResolvedValueOnce(new Response(JSON.stringify(me), { status: 200 }))
      // logout 204
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user?.email).toBe("a@b.com"));

    await act(async () => {
      await result.current.logout();
    });
    expect(result.current.user).toBeNull();
    expect(result.current.profiles).toEqual([]);
    vi.restoreAllMocks();
  });
});
