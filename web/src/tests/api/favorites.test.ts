import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { getFavorites, putFavorites, searchPlayers } from "@/api/favorites";

const API_URL = "http://localhost:8000";

const server = setupServer(
  http.get(`${API_URL}/api/favorites`, () =>
    HttpResponse.json({ favorite_player_ids: ["1", "2"], favorite_teams: ["KC"] })
  ),
  http.put(`${API_URL}/api/favorites`, async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json(body);
  }),
  http.get(`${API_URL}/api/players/search`, ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    if (!q) return new HttpResponse(null, { status: 400 });
    return HttpResponse.json([
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI" },
    ]);
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());

describe("favorites API client", () => {
  it("getFavorites returns the parsed payload", async () => {
    const fav = await getFavorites();
    expect(fav.favorite_player_ids).toEqual(["1", "2"]);
    expect(fav.favorite_teams).toEqual(["KC"]);
  });

  it("putFavorites echoes the persisted state", async () => {
    const saved = await putFavorites({ favorite_player_ids: ["3"], favorite_teams: ["BUF"] });
    expect(saved).toEqual({ favorite_player_ids: ["3"], favorite_teams: ["BUF"] });
  });

  it("searchPlayers returns matches", async () => {
    const results = await searchPlayers("Saq");
    expect(results).toHaveLength(1);
    expect(results[0].name).toBe("Saquon Barkley");
  });
});
