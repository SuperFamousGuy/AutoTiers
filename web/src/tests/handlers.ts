import { http, HttpResponse } from "msw";
import rules from "./fixtures/rules.json";
import dataStatus from "./fixtures/data-status.json";
import generateResponse from "./fixtures/generate-response.json";

const API_URL = "http://localhost:8000";

export const handlers = [
  http.get(`${API_URL}/api/rules`, () => HttpResponse.json(rules)),
  http.get(`${API_URL}/api/data/status`, () => HttpResponse.json(dataStatus)),
  http.post(`${API_URL}/api/generate`, () => HttpResponse.json(generateResponse)),
  http.post(`${API_URL}/api/generate/csv`, () =>
    new HttpResponse("rank,name\n1,Chase\n", {
      headers: { "Content-Type": "text/csv" },
    }),
  ),
  http.get(`${API_URL}/api/auth/me`, () => HttpResponse.text("", { status: 401 })),
  // New auth endpoints — default to sensible test responses.
  http.post(`${API_URL}/api/auth/password/forgot`, () =>
    HttpResponse.json({ detail: "If that email is registered, a reset link is on its way." }, { status: 202 }),
  ),
  http.post(`${API_URL}/api/auth/password/reset`, () =>
    HttpResponse.json({ detail: "Invalid or expired token" }, { status: 400 }),
  ),
  http.post(`${API_URL}/api/auth/password/change`, () =>
    new HttpResponse(null, { status: 204 }),
  ),
  http.post(`${API_URL}/api/auth/password/set`, () =>
    new HttpResponse(null, { status: 204 }),
  ),
  http.post(`${API_URL}/api/auth/email/resend-verification`, () =>
    HttpResponse.json({ detail: "Verification email sent." }, { status: 202 }),
  ),
  http.get(`${API_URL}/api/auth/email/verify`, () =>
    new HttpResponse(null, { status: 204 }),
  ),
];
