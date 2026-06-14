/**
 * Tests for PasswordManagementSection inside LinkedAccountsDialog.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { PasswordManagementSection } from "@/components/PasswordManagementSection";
import type { User } from "@/api/types";
import { server } from "@/tests/setup";

const API_URL = "http://localhost:8000";

const userWithPassword: User = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  yahoo_fantasy_connected: false,
  google_subject: null,
  last_active_profile_id: null,
  has_password: true,
  email_verified: true,
  password_changed_at: null,
};

const userOAuthOnly: User = {
  ...userWithPassword,
  has_password: false,
};

const userOAuthNoEmail: User = {
  ...userWithPassword,
  has_password: false,
  email: null,
};

describe("PasswordManagementSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing when user has no password and no email", () => {
    const { container } = render(
      <PasswordManagementSection user={userOAuthNoEmail} onRefresh={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows 'Change password' button when user has a password", () => {
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    expect(screen.getByRole("button", { name: /change password/i })).toBeInTheDocument();
  });

  it("shows 'Set password' button for OAuth-only users with email", () => {
    render(<PasswordManagementSection user={userOAuthOnly} onRefresh={vi.fn()} />);
    expect(screen.getByRole("button", { name: /set password/i })).toBeInTheDocument();
  });

  it("shows the user's email address", () => {
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    expect(screen.getByText(/alice@example.com/)).toBeInTheDocument();
  });

  it("expanding 'Change password' shows current, new, and confirm fields", async () => {
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /change password/i }));
    expect(document.getElementById("change-current-password")).toBeInTheDocument();
    expect(document.getElementById("change-new-password")).toBeInTheDocument();
    expect(document.getElementById("change-confirm-password")).toBeInTheDocument();
  });

  it("expanding 'Set password' shows new and confirm fields (no current-password field)", async () => {
    render(<PasswordManagementSection user={userOAuthOnly} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /set password/i }));
    expect(document.getElementById("set-new-password")).toBeInTheDocument();
    expect(document.getElementById("set-confirm-password")).toBeInTheDocument();
    expect(document.getElementById("change-current-password")).not.toBeInTheDocument();
  });

  it("Cancel button collapses the form", async () => {
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /change password/i }));
    expect(document.getElementById("change-current-password")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(document.getElementById("change-current-password")).not.toBeInTheDocument();
  });

  it("shows 'Passwords do not match' error on mismatch", async () => {
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /change password/i }));
    await u.type(document.getElementById("change-current-password")!, "OldPass123");
    await u.type(document.getElementById("change-new-password")!, "NewPass1234");
    await u.type(document.getElementById("change-confirm-password")!, "Different999");
    await u.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("calls POST /api/auth/password/change and shows success banner", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<PasswordManagementSection user={userWithPassword} onRefresh={onRefresh} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /change password/i }));
    await u.type(document.getElementById("change-current-password")!, "OldPass123456");
    await u.type(document.getElementById("change-new-password")!, "NewPass1234XX");
    await u.type(document.getElementById("change-confirm-password")!, "NewPass1234XX");
    await u.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/password updated/i)).toBeInTheDocument();
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("calls POST /api/auth/password/set for OAuth-only user", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<PasswordManagementSection user={userOAuthOnly} onRefresh={onRefresh} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /set password/i }));
    await u.type(document.getElementById("set-new-password")!, "NewPass1234XX");
    await u.type(document.getElementById("set-confirm-password")!, "NewPass1234XX");
    await u.click(screen.getByRole("button", { name: /^set password$/i }));

    // The success banner says "Password set. You can now log in with your email."
    expect(await screen.findByText(/you can now log in with your email/i)).toBeInTheDocument();
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("shows backend error message when change-password fails", async () => {
    server.use(
      http.post(`${API_URL}/api/auth/password/change`, () =>
        HttpResponse.json({ detail: "Current password is incorrect" }, { status: 400 }),
      ),
    );
    render(<PasswordManagementSection user={userWithPassword} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /change password/i }));
    await u.type(document.getElementById("change-current-password")!, "WrongOldPass");
    await u.type(document.getElementById("change-new-password")!, "NewPass1234XX");
    await u.type(document.getElementById("change-confirm-password")!, "NewPass1234XX");
    await u.click(screen.getByRole("button", { name: /^save$/i }));
    expect(await screen.findByText(/current password is incorrect/i)).toBeInTheDocument();
  });

  it("shows 'last changed' when password_changed_at is set", () => {
    const yesterday = new Date(Date.now() - 86400000).toISOString();
    render(
      <PasswordManagementSection
        user={{ ...userWithPassword, password_changed_at: yesterday }}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByText(/last changed/i)).toBeInTheDocument();
  });

  it("shows 'Last changed: never' when password_changed_at is null", () => {
    render(
      <PasswordManagementSection
        user={{ ...userWithPassword, password_changed_at: null }}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByText(/last changed: never/i)).toBeInTheDocument();
  });
});
