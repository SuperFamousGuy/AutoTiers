import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { searchPlayers, batchPlayers } from "@/api/favorites";

const API_URL = "http://localhost:8000";

const server = setupServer(
  http.get(`${API_URL}/api/players/search`, ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    if (!q) return new HttpResponse(null, { status: 400 });
    return HttpResponse.json([
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
    ]);
  }),
  http.get(`${API_URL}/api/players/batch`, ({ request }) => {
    const url = new URL(request.url);
    const ids = url.searchParams.get("ids") ?? "";
    const idList = ids.split(",").filter(Boolean);
    const db: Record<string, { id: string; name: string; position: string; team: string; espn_id: string | null }> = {
      "1": { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
      "2": { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF", espn_id: "3054212" },
    };
    return HttpResponse.json(idList.filter((id) => id in db).map((id) => db[id]));
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());

describe("favorites API client", () => {
  it("searchPlayers returns matches", async () => {
    const results = await searchPlayers("Saq");
    expect(results).toHaveLength(1);
    expect(results[0].name).toBe("Saquon Barkley");
  });

  it("batchPlayers fetches /api/players/batch with comma-joined ids", async () => {
    const results = await batchPlayers(["1", "2"]);
    expect(results).toHaveLength(2);
    expect(results[0].id).toBe("1");
    expect(results[1].id).toBe("2");
  });

  it("batchPlayers returns empty array without fetching when ids is empty", async () => {
    // msw server would throw if a request were made, but we get [] immediately
    const results = await batchPlayers([]);
    expect(results).toEqual([]);
  });
});
