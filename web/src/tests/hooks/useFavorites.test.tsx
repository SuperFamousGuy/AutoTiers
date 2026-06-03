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
});
