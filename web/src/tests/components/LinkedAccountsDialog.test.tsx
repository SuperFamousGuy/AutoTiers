import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import type { User, Profile } from "@/api/types";

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
  connectCbs: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

vi.mock("@/components/YahooConnectForm", () => ({
  YahooConnectForm: ({ profile, onLinked }: any) => (
    <div data-testid="yahoo-connect-form" onClick={() => onLinked({})}>
      Yahoo Connect Form for {profile.name}
    </div>
  ),
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

const activeProfile: Profile = {
  id: "p1",
  name: "My",
  settings_json: {},
  rules_json: {},
  linked_league: null,
};

const noop = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LinkedAccountsDialog", () => {
  it("renders with title 'Connect Your League'", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText("Connect Your League")).toBeInTheDocument();
  });

  it("renders a tab strip with all five platforms", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByRole("button", { name: /^sleeper$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^espn$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^yahoo$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^nfl fantasy$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^cbs$/i })).toBeInTheDocument();
  });

  it("default active tab is Sleeper — Sleeper username field is visible", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByLabelText(/sleeper username/i)).toBeInTheDocument();
  });

  it("clicking the ESPN tab shows the ESPN League ID field", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^espn$/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();
  });

  it("clicking the Yahoo tab shows the YahooConnectForm when activeProfile is set", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^yahoo$/i }));
    expect(await screen.findByTestId("yahoo-connect-form")).toBeInTheDocument();
  });

  it("Yahoo tab shows 'Select a profile' when no activeProfile is provided", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^yahoo$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });

  it("shows 'Select a profile' when Sleeper tab is active but no activeProfile is provided", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/select a profile/i)).toBeInTheDocument();
  });

  it("Google footer shows Link button when Google is not connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /^link google$/i })).toBeInTheDocument();
  });

  it("Google footer shows Unlink button when Google is connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /disconnect google/i })).toBeInTheDocument();
  });

  it("Unlink Google calls unlinkGoogle then onRefresh", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const refresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={refresh} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    await waitFor(() => expect(unlinkGoogle).toHaveBeenCalled());
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("shows the API error message when unlinkGoogle fails", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    const { ApiError } = await import("@/api/client");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "Cannot unlink last sign-in method"),
    );
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    expect(await screen.findByText(/last sign-in method/i)).toBeInTheDocument();
  });

  it("Link Google navigates to the authorize URL with intent=link", async () => {
    let assignedHref = "";
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, set href(v: string) { assignedHref = v; } },
    });
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^link google$/i }));
    expect(assignedHref).toContain("/api/auth/google/authorize");
    expect(assignedHref).toContain("intent=link");
    Object.defineProperty(window, "location", { writable: true, value: { href: "" } });
  });

  it("renders an initial error when provided", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop}
        initialError="This Google account is already linked to a different AutoTiers account." />,
    );
    expect(screen.getByText(/already linked/i)).toBeInTheDocument();
  });

  it("closing the dialog resets active tab to Sleeper", async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <LinkedAccountsDialog open={true} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^espn$/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();

    rerender(
      <LinkedAccountsDialog open={false} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    rerender(
      <LinkedAccountsDialog open={true} onOpenChange={onOpenChange} user={baseUser}
        onRefresh={vi.fn()} initialError={null} activeProfile={activeProfile} />,
    );
    expect(await screen.findByLabelText(/sleeper username/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });

  it("Yahoo tab onLinked callback calls onRefresh", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={onRefresh} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^yahoo$/i }));
    const form = await screen.findByTestId("yahoo-connect-form");
    await u.click(form);
    expect(onRefresh).toHaveBeenCalled();
  });

  it("CBS tab is enabled (no longer 'Coming Soon') and shows the connect form", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const cbsTab = screen.getByRole("button", { name: /^cbs$/i });
    expect(cbsTab).toBeEnabled();
    expect(screen.queryByText(/cbs sports.*coming soon/i)).not.toBeInTheDocument();
    const u = userEvent.setup();
    await u.click(cbsTab);
    expect(await screen.findByLabelText(/cbs email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/cbs password/i)).toBeInTheDocument();
  });

  it("CBS tab shows 'Select a profile' when no activeProfile is provided", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^cbs$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });

  it("NFL Fantasy tab is enabled (no longer 'Coming Soon') and shows the connect form", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    const nflTab = screen.getByRole("button", { name: /^nfl fantasy$/i });
    expect(nflTab).toBeEnabled();
    await u.click(nflTab);
    expect(screen.queryByText(/nfl fantasy.*coming soon/i)).not.toBeInTheDocument();
    expect(await screen.findByLabelText("League ID")).toBeInTheDocument();
    expect(screen.getByLabelText("Season")).toBeInTheDocument();
    // No credential field — NFL linking collects no login (the connect form
    // exposes only League ID + Season). The "no password field" assertion is
    // covered precisely in NflConnectForm.test.tsx; here we just confirm the
    // form replaced the Coming Soon stub.
  });

  it("NFL tab shows 'Select a profile' when no activeProfile is provided", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^nfl fantasy$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });
});
