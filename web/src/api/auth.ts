import { apiFetch, API_URL, ApiError } from "./client";
import type { MeResponse } from "./types";

export interface SignupBody {
  email: string;
  password: string;
  initial_settings?: Record<string, unknown>;
  initial_rules?: Record<string, Array<{ name: string; enabled: boolean; weight: number }>>;
}

export interface LoginBody {
  email: string;
  password: string;
}

export interface ForgotPasswordBody {
  email: string;
}

export interface ResetPasswordBody {
  token: string;
  new_password: string;
}

export interface ChangePasswordBody {
  current_password: string;
  new_password: string;
}

export interface SetPasswordBody {
  new_password: string;
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

async function unlinkProvider(path: string): Promise<void> {
  // Raw fetch because 204 No Content; check resp.ok so non-2xx surfaces.
  const resp = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
}

export function unlinkGoogle(): Promise<void> {
  return unlinkProvider("/api/auth/google/link");
}

export function unlinkYahoo(): Promise<void> {
  return unlinkProvider("/api/auth/yahoo/link");
}

export async function requestPasswordReset(body: ForgotPasswordBody): Promise<void> {
  // 202 response with a JSON body — use apiFetch but discard the result.
  await apiFetch("/api/auth/password/forgot", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function confirmPasswordReset(body: ResetPasswordBody): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/auth/password/reset", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function changePassword(body: ChangePasswordBody): Promise<void> {
  const resp = await fetch(`${API_URL}/api/auth/password/change`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
}

export async function setPassword(body: SetPasswordBody): Promise<void> {
  const resp = await fetch(`${API_URL}/api/auth/password/set`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
}

export async function resendVerificationEmail(): Promise<void> {
  // 202 — discard body
  await apiFetch("/api/auth/email/resend-verification", {
    method: "POST",
  });
}

export async function verifyEmail(token: string): Promise<void> {
  const resp = await fetch(
    `${API_URL}/api/auth/email/verify?token=${encodeURIComponent(token)}`,
    { credentials: "include" },
  );
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
}
