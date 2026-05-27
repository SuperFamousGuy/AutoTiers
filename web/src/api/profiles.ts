import { apiFetch, API_URL } from "./client";
import type { Profile, ProfilesListResponse } from "./types";

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

export async function deleteProfile(id: string): Promise<void> {
  await fetch(`${API_URL}/api/profiles/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function activateProfile(id: string): Promise<void> {
  await fetch(`${API_URL}/api/profiles/${id}/activate`, {
    method: "POST",
    credentials: "include",
  });
}
