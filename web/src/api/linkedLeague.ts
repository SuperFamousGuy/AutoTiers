import { apiFetch, API_URL, ApiError } from "./client";
import type { LinkedLeague, SleeperLeagueSummary, Profile } from "./types";

export interface YahooLeagueSummary {
  league_key: string;
  name: string;
  season: number;
  num_teams: number;
}

export interface LinkedLeagueResponse {
  linked_league: LinkedLeague;
  profile: Profile;
}

export function listSleeperLeagues(
  profileId: string,
  username: string,
  season: number,
): Promise<SleeperLeagueSummary[]> {
  const qs = new URLSearchParams({ username, season: String(season) }).toString();
  return apiFetch<SleeperLeagueSummary[]>(
    `/api/profiles/${profileId}/link/sleeper/leagues?${qs}`,
  );
}

export function connectSleeper(
  profileId: string,
  body: { username: string; league_id?: string; season?: number },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/sleeper`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function connectEspn(
  profileId: string,
  body: { league_id?: string; season?: number; swid?: string; espn_s2?: string },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/espn`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function refreshLink(profileId: string): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/refresh`,
    { method: "POST" },
  );
}

export async function disconnectLink(profileId: string): Promise<void> {
  // Raw fetch because 204 No Content; apiFetch would try to parse an empty body.
  const resp = await fetch(`${API_URL}/api/profiles/${profileId}/link`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}

export function listYahooLeagues(profileId: string): Promise<YahooLeagueSummary[]> {
  return apiFetch<YahooLeagueSummary[]>(`/api/profiles/${profileId}/link/yahoo/leagues`);
}

export function connectYahoo(
  profileId: string,
  body: { league_key: string; season: number },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/yahoo`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function connectCbs(
  profileId: string,
  body: { email: string; password: string; league_id: string },
): Promise<LinkedLeagueResponse> {
  return apiFetch<LinkedLeagueResponse>(
    `/api/profiles/${profileId}/link/cbs`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
