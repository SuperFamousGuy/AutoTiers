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
  await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
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
