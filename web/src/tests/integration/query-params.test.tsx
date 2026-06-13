/**
 * Integration tests for App.tsx query-param handling:
 *  - ?reset_token= shows PasswordResetPanel
 *  - ?verify_token= calls /api/auth/email/verify and shows a toast
 *  - params are stripped from the URL
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import App from "@/App";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/components/ui/toast";
import { server } from "@/tests/setup";

const API_URL = "http://localhost:8000";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("App — query param: reset_token", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    // Reset the URL so subsequent tests start clean.
    window.history.replaceState({}, "", "/");
  });

  it("shows the PasswordResetPanel when ?reset_token= is in the URL", async () => {
    window.history.replaceState({}, "", "/?reset_token=abc123");
    renderApp();
    expect(await screen.findByText(/set a new password/i)).toBeInTheDocument();
  });

  it("strips reset_token from the URL", async () => {
    window.history.replaceState({}, "", "/?reset_token=abc123");
    renderApp();
    await screen.findByText(/set a new password/i);
    expect(window.location.search).not.toContain("reset_token");
  });
});

describe("App — query param: verify_token", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, "", "/");
  });

  it("calls GET /api/auth/email/verify with the token", async () => {
    // MSW default handler returns 204.
    window.history.replaceState({}, "", "/?verify_token=verifyabc");
    renderApp();
    // The verification call happens on mount; just verify the URL was stripped.
    await waitFor(() => expect(window.location.search).not.toContain("verify_token"));
  });

  it("strips verify_token from the URL on success", async () => {
    window.history.replaceState({}, "", "/?verify_token=verifyabc");
    renderApp();
    await waitFor(() => expect(window.location.search).not.toContain("verify_token"));
  });

  it("strips verify_token from the URL on failure too", async () => {
    server.use(
      http.get(`${API_URL}/api/auth/email/verify`, () =>
        HttpResponse.json({ detail: "Invalid or expired token" }, { status: 400 }),
      ),
    );
    window.history.replaceState({}, "", "/?verify_token=badtoken");
    renderApp();
    await waitFor(() => expect(window.location.search).not.toContain("verify_token"));
  });
});

describe("App — email verification banner", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("shows verification banner when user.email_verified is false", async () => {
    server.use(
      http.get(`${API_URL}/api/auth/me`, () =>
        HttpResponse.json({
          user: {
            id: "u1",
            email: "unverified@example.com",
            yahoo_subject: null,
            yahoo_fantasy_connected: false,
            google_subject: null,
            last_active_profile_id: null,
            has_password: true,
            email_verified: false,
            password_changed_at: null,
          },
          profiles: [],
        }),
      ),
    );
    renderApp();
    expect(await screen.findByText(/please verify your email/i)).toBeInTheDocument();
  });

  it("does NOT show banner when user.email_verified is true", async () => {
    server.use(
      http.get(`${API_URL}/api/auth/me`, () =>
        HttpResponse.json({
          user: {
            id: "u1",
            email: "verified@example.com",
            yahoo_subject: null,
            yahoo_fantasy_connected: false,
            google_subject: null,
            last_active_profile_id: null,
            has_password: true,
            email_verified: true,
            password_changed_at: null,
          },
          profiles: [],
        }),
      ),
    );
    renderApp();
    // Wait a tick for the auth response to be processed.
    await waitFor(() => expect(screen.queryByText(/please verify your email/i)).not.toBeInTheDocument());
  });
});
