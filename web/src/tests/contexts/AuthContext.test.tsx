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

  it("applies the latest-issued refresh() even if an earlier call resolves last", async () => {
    // Reproduces #713: the mount refresh() (issued first, carrying a stale
    // pre-verification payload) resolves AFTER a second refresh() that carries
    // the fresh post-verification payload. The sequence guard must keep the
    // later-issued response and discard the older one regardless of order.
    const stale = { user: { id: "u1", email: "stale@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: null }, profiles: [] };
    const fresh = { user: { id: "u1", email: "fresh@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: "p1" }, profiles: [{ id: "p1" }] };

    let resolveFirst!: (r: Response) => void;
    let resolveSecond!: (r: Response) => void;
    const firstResp = new Promise<Response>((r) => { resolveFirst = r; });
    const secondResp = new Promise<Response>((r) => { resolveSecond = r; });

    vi.spyOn(global, "fetch")
      // mount refresh() — stale payload, still in flight
      .mockReturnValueOnce(firstResp as unknown as ReturnType<typeof fetch>)
      // second refresh() — fresh payload
      .mockReturnValueOnce(secondResp as unknown as ReturnType<typeof fetch>);

    const { result } = renderHook(() => useAuth(), { wrapper });
    // Mount refresh() is in flight; issue the second refresh().
    act(() => { void result.current.refresh(); });

    // Resolve the SECOND (later-issued) call first — its payload should apply.
    await act(async () => {
      resolveSecond(new Response(JSON.stringify(fresh), { status: 200 }));
    });
    await waitFor(() => expect(result.current.user?.email).toBe("fresh@b.com"));

    // Now resolve the FIRST (earlier-issued) call — it must be discarded.
    await act(async () => {
      resolveFirst(new Response(JSON.stringify(stale), { status: 200 }));
    });

    expect(result.current.user?.email).toBe("fresh@b.com");
    expect(result.current.profiles).toEqual([{ id: "p1" }]);
    expect(result.current.loading).toBe(false);
    vi.restoreAllMocks();
  });

  it("login survives a stale mount refresh() that resolves after it (#725)", async () => {
    // The mount refresh() is in flight (slow) when the user logs in. login()
    // resolves first with a real user; then the earlier mount refresh()
    // resolves with an anonymous payload. Because login() bumps the shared
    // sequence guard, the late refresh() must be discarded — the logged-in
    // user must survive.
    const loggedIn = { user: { id: "u1", email: "loggedin@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: "p1" }, profiles: [{ id: "p1" }] };

    let resolveMount!: (r: Response) => void;
    const mountResp = new Promise<Response>((r) => { resolveMount = r; });

    vi.spyOn(global, "fetch")
      // mount refresh() — anonymous payload, still in flight
      .mockReturnValueOnce(mountResp as unknown as ReturnType<typeof fetch>)
      // login() — resolves immediately with a real user
      .mockResolvedValueOnce(new Response(JSON.stringify(loggedIn), { status: 200 }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login({ email: "loggedin@b.com", password: "x" });
    });
    expect(result.current.user?.email).toBe("loggedin@b.com");

    // Late mount refresh() resolves with an anonymous payload — must be dropped.
    await act(async () => {
      resolveMount(new Response(JSON.stringify({ user: null, profiles: [] }), { status: 200 }));
    });
    expect(result.current.user?.email).toBe("loggedin@b.com");
    expect(result.current.profiles).toEqual([{ id: "p1" }]);
    // The discarded mount refresh() must not leave loading stuck (#725).
    expect(result.current.loading).toBe(false);
    vi.restoreAllMocks();
  });

  it("signup survives a stale mount refresh() that resolves after it (#725)", async () => {
    const signedUp = { user: { id: "u2", email: "signedup@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: null }, profiles: [{ id: "p2" }] };

    let resolveMount!: (r: Response) => void;
    const mountResp = new Promise<Response>((r) => { resolveMount = r; });

    vi.spyOn(global, "fetch")
      .mockReturnValueOnce(mountResp as unknown as ReturnType<typeof fetch>)
      .mockResolvedValueOnce(new Response(JSON.stringify(signedUp), { status: 201 }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.signup({ email: "signedup@b.com", password: "longenough123" });
    });
    expect(result.current.user?.email).toBe("signedup@b.com");

    await act(async () => {
      resolveMount(new Response(JSON.stringify({ user: null, profiles: [] }), { status: 200 }));
    });
    expect(result.current.user?.email).toBe("signedup@b.com");
    expect(result.current.profiles).toEqual([{ id: "p2" }]);
    expect(result.current.loading).toBe(false);
    vi.restoreAllMocks();
  });

  it("logout survives a stale mount refresh() that resolves after it (#725)", async () => {
    // The mount refresh() (carrying a still-authenticated payload) is in flight
    // when the user logs out. logout() resolves first and clears state; the late
    // mount refresh() must not resurrect the logged-out user.
    const stillAuthed = { user: { id: "u1", email: "authed@b.com", yahoo_subject: null, google_subject: null, last_active_profile_id: null }, profiles: [{ id: "p1" }] };

    let resolveMount!: (r: Response) => void;
    const mountResp = new Promise<Response>((r) => { resolveMount = r; });

    vi.spyOn(global, "fetch")
      // mount refresh() — authenticated payload, still in flight
      .mockReturnValueOnce(mountResp as unknown as ReturnType<typeof fetch>)
      // logout() 204
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.logout();
    });
    expect(result.current.user).toBeNull();

    // Late mount refresh() resolves with an authenticated payload — must be dropped.
    await act(async () => {
      resolveMount(new Response(JSON.stringify(stillAuthed), { status: 200 }));
    });
    expect(result.current.user).toBeNull();
    expect(result.current.profiles).toEqual([]);
    expect(result.current.loading).toBe(false);
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
