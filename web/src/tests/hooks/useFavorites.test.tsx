import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useFavorites } from "@/hooks/useFavorites";

const API_URL = "http://localhost:8000";

let saved: any = null;

const server = setupServer(
  http.get(`${API_URL}/api/favorites`, () =>
    HttpResponse.json({ favorite_player_ids: ["initial"], favorite_teams: ["KC"] })
  ),
  http.put(`${API_URL}/api/favorites`, async ({ request }) => {
    saved = await request.json();
    return HttpResponse.json(saved);
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());
beforeEach(() => { saved = null; });

describe("useFavorites", () => {
  it("fetches favorites on mount when authenticated", async () => {
    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));
  });

  it("does NOT fetch when unauthenticated", async () => {
    const { result } = renderHook(() => useFavorites(false));
    expect(result.current.favorites.favorite_player_ids).toEqual([]);
    expect(result.current.favorites.favorite_teams).toEqual([]);
  });

  it("save updates state optimistically and round-trips", async () => {
    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));
    await act(async () => {
      await result.current.save({ favorite_player_ids: ["new"], favorite_teams: ["BUF"] });
    });
    expect(saved).toEqual({ favorite_player_ids: ["new"], favorite_teams: ["BUF"] });
    expect(result.current.favorites.favorite_player_ids).toEqual(["new"]);
  });

  it("reverts to the last server truth and rethrows when a save fails", async () => {
    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));

    server.use(
      http.put(`${API_URL}/api/favorites`, () => new HttpResponse(null, { status: 500 })),
    );

    await act(async () => {
      await expect(
        result.current.save({ favorite_player_ids: ["nope"], favorite_teams: [] }),
      ).rejects.toBeTruthy();
    });

    // Optimistic "nope" was rolled back to the loaded server state.
    expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]);
    expect(result.current.favorites.favorite_teams).toEqual(["KC"]);
  });

  it("serializes overlapping saves: the second PUT waits for the first, then wins", async () => {
    const putBodies: any[] = [];
    let releaseFirst!: () => void;
    const firstGate = new Promise<void>((r) => { releaseFirst = r; });
    let putCount = 0;
    server.use(
      http.put(`${API_URL}/api/favorites`, async ({ request }) => {
        const body: any = await request.json();
        putBodies.push(body);
        putCount += 1;
        if (putCount === 1) await firstGate; // hold the first response open
        return HttpResponse.json(body);
      }),
    );

    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));

    // Fire A, then B before A's PUT resolves.
    let bPromise!: Promise<void>;
    act(() => {
      void result.current.save({ favorite_player_ids: ["A"], favorite_teams: [] });
      bPromise = result.current.save({ favorite_player_ids: ["B"], favorite_teams: [] });
    });

    // Only A's PUT has been issued; B is queued, not raced concurrently.
    await waitFor(() => expect(putCount).toBe(1));
    expect(putBodies).toHaveLength(1);
    expect(putBodies[0].favorite_player_ids).toEqual(["A"]);
    // Optimistic UI already reflects the latest edit (B).
    expect(result.current.favorites.favorite_player_ids).toEqual(["B"]);

    // Release A; B now fires with B's own payload as the last write.
    await act(async () => {
      releaseFirst();
      await bPromise;
    });
    expect(putCount).toBe(2);
    expect(putBodies[1].favorite_player_ids).toEqual(["B"]);
    expect(result.current.favorites.favorite_player_ids).toEqual(["B"]);
  });

  it("coalesces rapid clicks: only the latest queued payload is sent after the in-flight write", async () => {
    const putBodies: any[] = [];
    let releaseFirst!: () => void;
    const firstGate = new Promise<void>((r) => { releaseFirst = r; });
    let putCount = 0;
    server.use(
      http.put(`${API_URL}/api/favorites`, async ({ request }) => {
        const body: any = await request.json();
        putBodies.push(body);
        putCount += 1;
        if (putCount === 1) await firstGate;
        return HttpResponse.json(body);
      }),
    );

    const { result } = renderHook(() => useFavorites(true));
    await waitFor(() => expect(result.current.favorites.favorite_player_ids).toEqual(["initial"]));

    let last!: Promise<void>;
    act(() => {
      void result.current.save({ favorite_player_ids: ["A"], favorite_teams: [] });
      void result.current.save({ favorite_player_ids: ["B"], favorite_teams: [] });
      last = result.current.save({ favorite_player_ids: ["C"], favorite_teams: [] });
    });

    await waitFor(() => expect(putCount).toBe(1));

    await act(async () => {
      releaseFirst();
      await last;
    });

    // B was superseded by C before it fired: server saw A then C, never B.
    expect(putCount).toBe(2);
    expect(putBodies.map((b) => b.favorite_player_ids)).toEqual([["A"], ["C"]]);
    expect(result.current.favorites.favorite_player_ids).toEqual(["C"]);
  });
});
