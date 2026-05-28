import { apiFetch, API_URL, ApiError } from "./client";
import type { MeResponse } from "./types";

export interface SignupBody {
  email: string;
  password: string;
  initial_settings?: Record<string, unknown>;
  initial_rules?: Array<Record<string, unknown>>;
}

export interface LoginBody {
  email: string;
  password: string;
}

export function signup(body: SignupBody): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function login(body: LoginBody): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function logout(): Promise<void> {
  // Raw fetch (not apiFetch) because logout returns 204 No Content;
  // apiFetch would try to parse an empty body as JSON. Check resp.ok
  // explicitly so non-2xx surfaces as ApiError.
  const resp = await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}

export async function getMe(): Promise<MeResponse | null> {
  try {
    return await apiFetch<MeResponse>("/api/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export function yahooAuthorizeUrl(): string {
  return `${API_URL}/api/auth/yahoo/authorize`;
}

export function googleAuthorizeUrl(): string {
  return `${API_URL}/api/auth/google/authorize`;
}
