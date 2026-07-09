/**
 * Tests for the new Account section in LinkedAccountsDialog
 * (password management row + Google row).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import type { User } from "@/api/types";

vi.mock("@/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/api/auth")>("@/api/auth");
  return {
    ...actual,
    unlinkGoogle: vi.fn(),
    unlinkYahoo: vi.fn(),
    googleAuthorizeUrl: () => "http://localhost:8000/api/auth/google/authorize",
    yahooAuthorizeUrl: () => "http://localhost:8000/api/auth/yahoo/authorize",
  };
});

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
  connectEspn: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

vi.mock("@/components/YahooConnectForm", () => ({
  YahooConnectForm: () => <div data-testid="yahoo-connect-form" />,
}));

const baseUser: User = {
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

const noop = vi.fn();

beforeEach(() => vi.clearAllMocks());

describe("LinkedAccountsDialog — Account section", () => {
  it("renders an 'Account' section heading", () => {
    render(
      <LinkedAccountsDialog open user={baseUser} onOpenChange={noop} onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/^account$/i)).toBeInTheDocument();
  });

  it("renders a 'Fantasy leagues' section heading", () => {
    render(
      <LinkedAccountsDialog open user={baseUser} onOpenChange={noop} onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/^fantasy leagues$/i)).toBeInTheDocument();
  });

  it("shows 'Change password' button for user with a password", () => {
    render(
      <LinkedAccountsDialog open user={baseUser} onOpenChange={noop} onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /change password/i })).toBeInTheDocument();
  });

  it("shows 'Set password' button for OAuth-only user with email", () => {
    render(
      <LinkedAccountsDialog
        open
        user={{ ...baseUser, has_password: false }}
        onOpenChange={noop}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByRole("button", { name: /set password/i })).toBeInTheDocument();
  });

  it("hides password section for OAuth-only user with no email", () => {
    render(
      <LinkedAccountsDialog
        open
        user={{ ...baseUser, has_password: false, email: null }}
        onOpenChange={noop}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.queryByRole("button", { name: /change password/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /set password/i })).not.toBeInTheDocument();
  });

  it("Google row shows Link button when not connected", () => {
    render(
      <LinkedAccountsDialog open user={baseUser} onOpenChange={noop} onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /^link google$/i })).toBeInTheDocument();
  });

  it("Google row shows Unlink button when connected", () => {
    render(
      <LinkedAccountsDialog
        open
        user={{ ...baseUser, google_subject: "g-sub" }}
        onOpenChange={noop}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByRole("button", { name: /disconnect google/i })).toBeInTheDocument();
  });

  it("still renders all 5 fantasy-league platform tabs", () => {
    render(
      <LinkedAccountsDialog open user={baseUser} onOpenChange={noop} onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^espn$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^yahoo$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^nfl fantasy$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^cbs$/i })).toBeInTheDocument();
  });
});
