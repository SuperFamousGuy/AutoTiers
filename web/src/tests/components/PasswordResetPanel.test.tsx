/**
 * Tests for PasswordResetPanel — the inline panel rendered when ?reset_token=
 * is in the URL.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PasswordResetPanel } from "@/components/PasswordResetPanel";
import { AuthProvider } from "@/contexts/AuthContext";

const API_URL = "http://localhost:8000";

function renderPanel(props?: Partial<React.ComponentProps<typeof PasswordResetPanel>>) {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response("", { status: 401 }));
  return render(
    <AuthProvider>
      <PasswordResetPanel
        token="test-token-abc"
        onDismiss={() => {}}
        onRequestNewLink={() => {}}
        {...props}
      />
    </AuthProvider>,
  );
}

describe("PasswordResetPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the 'Set a new password' heading", () => {
    renderPanel();
    expect(screen.getByText(/set a new password/i)).toBeInTheDocument();
  });

  it("has new-password and confirm-password fields", () => {
    renderPanel();
    expect(document.getElementById("reset-new-password")).toBeInTheDocument();
    expect(document.getElementById("reset-confirm-password")).toBeInTheDocument();
  });

  it("shows 'Passwords do not match' when confirm doesn't match", async () => {
    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "StrongPass123");
    await u.type(document.getElementById("reset-confirm-password")!, "DifferentPass123");
    await u.click(screen.getByRole("button", { name: /save new password/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("shows 'at least 10 characters' when password is too short", async () => {
    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "short");
    await u.type(document.getElementById("reset-confirm-password")!, "short");
    await u.click(screen.getByRole("button", { name: /save new password/i }));
    // The strength hint and the submit-time error both mention length.
    const msgs = await screen.findAllByText(/at least 10 characters/i);
    expect(msgs.length).toBeGreaterThanOrEqual(1);
  });

  it("calls POST /api/auth/password/reset with the token and new password", async () => {
    const successResponse = {
      user: {
        id: "u1",
        email: "user@example.com",
        yahoo_subject: null,
        yahoo_fantasy_connected: false,
        google_subject: null,
        last_active_profile_id: null,
        has_password: true,
        email_verified: true,
        password_changed_at: null,
      },
      profiles: [],
    };
    const fetchSpy = vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 })) // /me on mount
      .mockResolvedValueOnce(
        new Response(JSON.stringify(successResponse), { status: 200 }),
      ) // reset
      .mockResolvedValueOnce(
        new Response(JSON.stringify(successResponse), { status: 200 }),
      ); // refresh /me

    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "NewStrongPass99");
    await u.type(document.getElementById("reset-confirm-password")!, "NewStrongPass99");
    await u.click(screen.getByRole("button", { name: /save new password/i }));

    const resetCall = await waitFor(() => {
      const call = fetchSpy.mock.calls.find((c) => String(c[0]).includes("/api/auth/password/reset"));
      expect(call).toBeDefined();
      return call!;
    });

    const body = JSON.parse(String(resetCall[1]!.body));
    expect(body).toMatchObject({ token: "test-token-abc", new_password: "NewStrongPass99" });
  });

  it("shows success message after a successful reset", async () => {
    const successResponse = {
      user: {
        id: "u1",
        email: "user@example.com",
        yahoo_subject: null,
        yahoo_fantasy_connected: false,
        google_subject: null,
        last_active_profile_id: null,
        has_password: true,
        email_verified: true,
        password_changed_at: null,
      },
      profiles: [],
    };
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(successResponse), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(successResponse), { status: 200 }));

    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "NewStrongPass99");
    await u.type(document.getElementById("reset-confirm-password")!, "NewStrongPass99");
    await u.click(screen.getByRole("button", { name: /save new password/i }));

    expect(await screen.findByText(/your password has been updated/i)).toBeInTheDocument();
  });

  it("shows token-expired error when backend returns 'This link has expired'", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "This link has expired" }), { status: 400 }),
      );

    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "NewStrongPass99");
    await u.type(document.getElementById("reset-confirm-password")!, "NewStrongPass99");
    await u.click(screen.getByRole("button", { name: /save new password/i }));

    expect(await screen.findByText(/reset link has expired/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /request new link/i })).toBeInTheDocument();
  });

  it("shows already-used error when backend returns 'This link has already been used'", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "This link has already been used" }), { status: 400 }),
      );

    renderPanel();
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "NewStrongPass99");
    await u.type(document.getElementById("reset-confirm-password")!, "NewStrongPass99");
    await u.click(screen.getByRole("button", { name: /save new password/i }));

    expect(await screen.findByText(/already been used/i)).toBeInTheDocument();
  });

  it("'Request new link' button calls onRequestNewLink", async () => {
    const onRequestNewLink = vi.fn();
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "This link has expired" }), { status: 400 }),
      );

    renderPanel({ onRequestNewLink });
    const u = userEvent.setup();
    await u.type(document.getElementById("reset-new-password")!, "NewStrongPass99");
    await u.type(document.getElementById("reset-confirm-password")!, "NewStrongPass99");
    await u.click(screen.getByRole("button", { name: /save new password/i }));

    await screen.findByText(/reset link has expired/i);
    await u.click(screen.getByRole("button", { name: /request new link/i }));
    expect(onRequestNewLink).toHaveBeenCalled();
  });
});
