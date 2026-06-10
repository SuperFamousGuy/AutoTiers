import { describe, it, expect, vi, afterEach } from "vitest";
import {
  listSleeperLeagues,
  connectSleeper,
  connectEspn,
  refreshLink,
  disconnectLink,
} from "@/api/linkedLeague";
import { ApiError } from "@/api/client";

const PID = "00000000-0000-0000-0000-000000000001";

describe("linkedLeague API", () => {
  afterEach(() => vi.restoreAllMocks());

  it("listSleeperLeagues GETs the leagues endpoint", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify([{ id: "L1", name: "Champs", season: 2026 }]), { status: 200 }),
    );
    const result = await listSleeperLeagues(PID, "alice", 2026);
    expect(String(spy.mock.calls[0][0])).toContain(
      `/api/profiles/${PID}/link/sleeper/leagues?username=alice&season=2026`,
    );
    expect(result).toEqual([{ id: "L1", name: "Champs", season: 2026 }]);
  });

  it("connectSleeper POSTs body and returns updated profile", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "sleeper", league_id: "L1",
          league_metadata_json: { name: "Champs", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-01-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: {}, linked_league: null },
      }), { status: 200 }),
    );
    const out = await connectSleeper(PID, { username: "alice", league_id: "L1", season: 2026 });
    expect(String(spy.mock.calls[0][0])).toContain(`/api/profiles/${PID}/link/sleeper`);
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(out.linked_league.provider).toBe("sleeper");
  });

  it("connectEspn POSTs and returns updated profile", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "espn", league_id: "12345",
          league_metadata_json: { name: "ESPN League", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-01-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: {}, linked_league: null },
      }), { status: 200 }),
    );
    const out = await connectEspn(PID, { league_id: "12345", season: 2026, swid: "{x}", espn_s2: "y" });
    expect(out.linked_league.provider).toBe("espn");
  });

  it("disconnectLink DELETEs and returns void on 204", async () => {
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    await disconnectLink(PID);
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("refreshLink POSTs and returns updated profile", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({
        linked_league: { profile_id: PID, provider: "sleeper", league_id: "L1",
          league_metadata_json: { name: "New", season: 2026 },
          keepers_json: [], adp_json: null, last_synced_at: "2026-02-01T00:00:00Z" },
        profile: { id: PID, name: "My", settings_json: {}, rules_json: {}, linked_league: null },
      }), { status: 200 }),
    );
    const out = await refreshLink(PID);
    expect(out.linked_league.league_metadata_json?.name).toBe("New");
  });

  it("connectSleeper throws ApiError on 404", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response("not found", { status: 404 }),
    );
    await expect(
      connectSleeper(PID, { username: "ghost", league_id: "L1", season: 2026 }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("Yahoo Fantasy API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("listYahooLeagues GETs /api/profiles/{id}/link/yahoo/leagues", async () => {
    const { listYahooLeagues } = await import("@/api/linkedLeague");
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify([{ league_key: "423.l.1", name: "Test League", season: 2024, num_teams: 12 }]),
        { status: 200 },
      ),
    );
    const result = await listYahooLeagues(PID);
    expect(String(spy.mock.calls[0][0])).toContain(`/api/profiles/${PID}/link/yahoo/leagues`);
    expect(result[0].league_key).toBe("423.l.1");
  });

  it("connectYahoo POSTs league_key and season to /api/profiles/{id}/link/yahoo", async () => {
    const { connectYahoo } = await import("@/api/linkedLeague");
    const spy = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          linked_league: { profile_id: PID, provider: "yahoo", league_id: "423.l.1",
            league_metadata_json: { name: "Test League", season: 2024 },
            keepers_json: [], adp_json: null, last_synced_at: "" },
          profile: { id: PID, name: "My", settings_json: {}, rules_json: [], linked_league: null },
        }),
        { status: 200 },
      ),
    );
    const out = await connectYahoo(PID, { league_key: "423.l.1", season: 2024 });
    expect(String(spy.mock.calls[0][0])).toContain(`/api/profiles/${PID}/link/yahoo`);
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    const body = JSON.parse(spy.mock.calls[0][1]?.body as string);
    expect(body.league_key).toBe("423.l.1");
    expect(out.linked_league.provider).toBe("yahoo");
  });
});
