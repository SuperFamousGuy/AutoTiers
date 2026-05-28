import { apiFetch, API_URL, ApiError } from "./client";
import type { Profile, ProfilesListResponse } from "./types";


/** 204 endpoint helper: raw fetch (no JSON parse), with ApiError on non-2xx. */
async function _voidFetch(path: string, method: string): Promise<void> {
  const resp = await fetch(`${API_URL}${path}`, { method, credentials: "include" });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}

export interface ProfileCreateBody {
  name: string;
  settings_json: Record<string, unknown>;
  rules_json: Array<Record<string, unknown>>;
}

export interface ProfileUpdateBody {
  name?: string;
  settings_json?: Record<string, unknown>;
  rules_json?: Array<Record<string, unknown>>;
}

export function listProfiles(): Promise<ProfilesListResponse> {
  return apiFetch<ProfilesListResponse>("/api/profiles");
}

export function createProfile(body: ProfileCreateBody): Promise<Profile> {
  return apiFetch<Profile>("/api/profiles", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProfile(id: string, body: ProfileUpdateBody): Promise<Profile> {
  return apiFetch<Profile>(`/api/profiles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteProfile(id: string): Promise<void> {
  return _voidFetch(`/api/profiles/${id}`, "DELETE");
}

export function activateProfile(id: string): Promise<void> {
  return _voidFetch(`/api/profiles/${id}/activate`, "POST");
}
