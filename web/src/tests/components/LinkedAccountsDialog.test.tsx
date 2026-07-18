import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import type { User, Profile, LinkedLeague } from "@/api/types";

// unlinkGoogle is mocked so the Google tests can assert at the api-module level.
// unlinkYahoo is deliberately left as the REAL implementation so the Yahoo
// tests can assert the fetch-level request (DELETE /api/auth/yahoo/link),
// per issue #558's acceptance criteria.
vi.mock("@/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/api/auth")>("@/api/auth");
  return {
    ...actual,
    unlinkGoogle: vi.fn(),
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
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^espn$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^yahoo$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^nfl fantasy$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^cbs$/i })).toBeInTheDocument();
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
    await u.click(screen.getByRole("tab", { name: /^espn$/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();
  });

  it("clicking the Yahoo tab shows the YahooConnectForm when activeProfile is set", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /^yahoo$/i }));
    expect(await screen.findByTestId("yahoo-connect-form")).toBeInTheDocument();
  });

  it("Yahoo tab shows 'Select a profile' when no activeProfile is provided", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /^yahoo$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });

  it("shows 'Select a profile' when Sleeper tab is active but no activeProfile is provided", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/select a profile/i)).toBeInTheDocument();
  });

  // --- In-dialog "no active profile" resolution (issue #559) ---
  // The header profile picker is unreachable behind this focus-trapping modal,
  // so the empty state must offer an action that actually resolves the blocker.
  it("empty state lets the user pick an existing profile without leaving the dialog", async () => {
    const onSelectProfile = vi.fn();
    const profiles: Profile[] = [
      { ...activeProfile, id: "p1", name: "Redraft" },
      { ...activeProfile, id: "p2", name: "Dynasty" },
    ];
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        profiles={profiles} onSelectProfile={onSelectProfile} onCreateProfile={noop} />,
    );
    // Sleeper is the default tab and needs a profile, so the empty state shows.
    expect(screen.getByText(/select a profile to connect/i)).toBeInTheDocument();
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: "Dynasty" }));
    expect(onSelectProfile).toHaveBeenCalledWith("p2");
  });

  it("empty state offers to create a profile when the user has none", async () => {
    const onCreateProfile = vi.fn();
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        profiles={[]} onSelectProfile={noop} onCreateProfile={onCreateProfile} />,
    );
    expect(screen.getByText(/create a profile to connect/i)).toBeInTheDocument();
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^create a profile$/i }));
    expect(onCreateProfile).toHaveBeenCalled();
  });

  it("the in-dialog profile action is offered on every provider tab that needs a profile", async () => {
    const onSelectProfile = vi.fn();
    const profiles: Profile[] = [{ ...activeProfile, id: "p1", name: "Redraft" }];
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        profiles={profiles} onSelectProfile={onSelectProfile} onCreateProfile={noop} />,
    );
    const u = userEvent.setup();
    for (const tab of [/^espn$/i, /^yahoo$/i, /^nfl fantasy$/i, /^cbs$/i]) {
      await u.click(screen.getByRole("tab", { name: tab }));
      expect(await screen.findByRole("button", { name: "Redraft" })).toBeInTheDocument();
    }
  });

  it("falls back to the static message when no profile actions are wired", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByText(/select a profile above/i)).toBeInTheDocument();
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

  it("unwraps the FastAPI JSON detail (not the raw blob) when unlinkGoogle fails", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    const { ApiError } = await import("@/api/client");
    // The real shape: DELETE /api/auth/google/link raises HTTPException(400,
    // detail=...), so apiFetch/unlinkProvider store the JSON envelope as the
    // ApiError message. Regression for #642: the user must read the sentence,
    // not the JSON braces.
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, JSON.stringify({ detail: "Cannot unlink last sign-in method" })),
    );
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    const err = await screen.findByText(/cannot unlink last sign-in method/i);
    // The extracted sentence renders, and the JSON envelope does not leak through.
    expect(err).toHaveTextContent("Cannot unlink last sign-in method");
    expect(err.textContent).not.toMatch(/[{}[\]]|detail/);
  });

  it("falls back to the generic message when unlinkGoogle fails with a non-ApiError", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new TypeError("Failed to fetch"),
    );
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    expect(await screen.findByText(/disconnect failed\. please try again\./i)).toBeInTheDocument();
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

  // --- Yahoo sign-in identity row (issue #558) ---
  // yahoo_subject is the OAuth SIGN-IN identity, distinct from a linked fantasy
  // league. The Account section must expose Link/Unlink for it, mirroring Google.
  it("Yahoo account row shows Link button when Yahoo sign-in is not connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /^link yahoo$/i })).toBeInTheDocument();
  });

  it("Yahoo account row shows Unlink button when Yahoo sign-in is connected", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, yahoo_subject: "y-sub" }}
        onRefresh={noop} initialError={null} />,
    );
    expect(screen.getByRole("button", { name: /disconnect yahoo/i })).toBeInTheDocument();
  });

  it("Unlink Yahoo fires DELETE /api/auth/yahoo/link then calls onRefresh", async () => {
    // Fetch-level mock (not an api-module spy): asserts the real unlinkYahoo()
    // hits the reachable backend endpoint, and that it is unlinkYahoo — NOT
    // disconnectLink (the fantasy-league unlink) — that runs.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      text: () => Promise.resolve(""),
    });
    vi.stubGlobal("fetch", fetchMock);
    const refresh = vi.fn().mockResolvedValueOnce(undefined);
    try {
      render(
        <LinkedAccountsDialog open={true} onOpenChange={noop}
          user={{ ...baseUser, yahoo_subject: "y-sub" }}
          onRefresh={refresh} initialError={null} />,
      );
      const u = userEvent.setup();
      await u.click(screen.getByRole("button", { name: /disconnect yahoo/i }));
      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      const [url, init] = fetchMock.mock.calls[0];
      expect(String(url)).toContain("/api/auth/yahoo/link");
      expect(init).toMatchObject({ method: "DELETE" });
      await waitFor(() => expect(refresh).toHaveBeenCalled());
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("unwraps the FastAPI JSON detail (not the raw blob) when unlinkYahoo fails", async () => {
    // The real backend body for the last-sign-in-method rejection is a JSON
    // envelope, which unlinkProvider stores verbatim as ApiError.message.
    // Regression for #642: the extracted sentence renders, not the JSON.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      text: () =>
        Promise.resolve(JSON.stringify({ detail: "Cannot unlink last sign-in method" })),
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(
        <LinkedAccountsDialog open={true} onOpenChange={noop}
          user={{ ...baseUser, yahoo_subject: "y-sub" }}
          onRefresh={noop} initialError={null} />,
      );
      const u = userEvent.setup();
      await u.click(screen.getByRole("button", { name: /disconnect yahoo/i }));
      const err = await screen.findByText(/cannot unlink last sign-in method/i);
      expect(err).toHaveTextContent("Cannot unlink last sign-in method");
      expect(err.textContent).not.toMatch(/[{}[\]]|detail/);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("Link Yahoo navigates to the authorize URL with intent=link", async () => {
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
    await u.click(screen.getByRole("button", { name: /^link yahoo$/i }));
    expect(assignedHref).toContain("/api/auth/yahoo/authorize");
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
    await u.click(screen.getByRole("tab", { name: /^espn$/i }));
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

  // --- Default tab follows the already-linked provider (issue #788) ---
  // Reopening "Connect Your League" to check/refresh/disconnect an existing
  // connection should land on that provider's tab, not the unrelated Sleeper
  // one. The default is recomputed on each open from the active profile's
  // linked provider, falling back to Sleeper when nothing is linked.
  const linkedLeague = (
    provider: LinkedLeague["provider"],
  ): LinkedLeague => ({
    profile_id: "p1",
    provider,
    league_id: "L1",
    league_metadata_json: { name: "My League", season: 2024 },
    keepers_json: null,
    adp_json: null,
    last_synced_at: "",
  });

  it("opens on the ESPN tab when the active profile has a linked ESPN league", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: linkedLeague("espn") }} />,
    );
    expect(
      screen.getByRole("tab", { name: /^espn, league connected$/i }),
    ).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    // The ESPN panel shows its Connected state (Disconnect action) without any
    // click — the whole point of landing on the linked provider's tab.
    expect(screen.getByRole("button", { name: /disconnect espn/i })).toBeInTheDocument();
  });

  it("opens on the CBS tab when a CBS league is linked", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: linkedLeague("cbs") }} />,
    );
    expect(
      screen.getByRole("tab", { name: /^cbs, league connected$/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("opens on the NFL tab when an NFL league is linked", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: linkedLeague("nfl") }} />,
    );
    expect(
      screen.getByRole("tab", { name: /^nfl fantasy, league connected$/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("still defaults to Sleeper when nothing is linked", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByLabelText(/sleeper username/i)).toBeInTheDocument();
  });

  it("defaults to Sleeper when the linked provider isn't one of the tabs (defensive)", () => {
    // A provider value outside the five tabs (e.g. a future/legacy platform)
    // must not leave the dialog with no selected tab — fall back to Sleeper.
    const unknownLeague = {
      ...linkedLeague("espn"),
      provider: "draftkings",
    } as unknown as LinkedLeague;
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: unknownLeague }} />,
    );
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("reflects the newly-active profile's provider after switching profiles while closed", async () => {
    const espnProfile: Profile = {
      ...activeProfile, id: "p1", linked_league: linkedLeague("espn"),
    };
    const cbsProfile: Profile = {
      ...activeProfile, id: "p2", linked_league: linkedLeague("cbs"),
    };
    const { rerender } = render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={espnProfile} />,
    );
    expect(
      screen.getByRole("tab", { name: /^espn, league connected$/i }),
    ).toHaveAttribute("aria-selected", "true");

    // Close, switch the active profile to the CBS one, then reopen.
    rerender(
      <LinkedAccountsDialog open={false} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={espnProfile} />,
    );
    rerender(
      <LinkedAccountsDialog open={false} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={cbsProfile} />,
    );
    rerender(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={cbsProfile} />,
    );
    // Lands on the newly-active CBS provider, not the stale ESPN one.
    expect(
      await screen.findByRole("tab", { name: /^cbs, league connected$/i }),
    ).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /^espn$/i })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("Yahoo tab onLinked callback calls onRefresh", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={onRefresh} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("tab", { name: /^yahoo$/i }));
    const form = await screen.findByTestId("yahoo-connect-form");
    await u.click(form);
    expect(onRefresh).toHaveBeenCalled();
  });

  it("CBS tab is enabled (no longer 'Coming Soon') and shows the connect form", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const cbsTab = screen.getByRole("tab", { name: /^cbs$/i });
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
    await u.click(screen.getByRole("tab", { name: /^cbs$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });

  it("NFL Fantasy tab is enabled (no longer 'Coming Soon') and shows the connect form", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const u = userEvent.setup();
    const nflTab = screen.getByRole("tab", { name: /^nfl fantasy$/i });
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
    await u.click(screen.getByRole("tab", { name: /^nfl fantasy$/i }));
    expect(await screen.findByText(/select a profile/i)).toBeInTheDocument();
  });

  // --- Connected-dot semantics (issue #522) ---
  // The green dot means the same thing for every provider: an active league is
  // linked to the profile. Yahoo's OAuth sign-in alone must NOT light it.
  const yahooLeague = (): Profile["linked_league"] => ({
    profile_id: "p1",
    provider: "yahoo",
    league_id: "423.l.1",
    league_metadata_json: { name: "My League", season: 2024 },
    keepers_json: null,
    adp_json: null,
    last_synced_at: "",
  });

  it("Yahoo tab dot does NOT light on OAuth sign-in alone (no league linked)", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, yahoo_subject: "y-sub", yahoo_fantasy_connected: true }}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const yahooTab = screen.getByRole("tab", { name: /^yahoo$/i });
    expect(yahooTab.querySelector("span.bg-green-500")).toBeNull();
  });

  it("Yahoo tab dot lights only when a Yahoo league is linked to the active profile", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop}
        user={{ ...baseUser, yahoo_subject: "y-sub", yahoo_fantasy_connected: true }}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: yahooLeague() }} />,
    );
    // Accessible name gains the ", league connected" suffix once linked (#665).
    const yahooTab = screen.getByRole("tab", { name: /^yahoo, league connected$/i });
    expect(yahooTab.querySelector("span.bg-green-500")).not.toBeNull();
  });

  it("only the tab whose provider is linked shows the dot (no regression for other providers)", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{
          ...activeProfile,
          linked_league: { ...yahooLeague()!, provider: "sleeper", league_id: "s1" },
        }} />,
    );
    expect(
      screen
        .getByRole("tab", { name: /^sleeper, league connected$/i })
        .querySelector("span.bg-green-500"),
    ).not.toBeNull();
    expect(
      screen.getByRole("tab", { name: /^yahoo$/i }).querySelector("span.bg-green-500"),
    ).toBeNull();
  });

  // --- Connected-state announcement to assistive tech (issue #665) ---
  // The green dot is aria-hidden, so the connected state must reach screen
  // readers through the tab's accessible name, not the visual dot alone.
  it("a connected tab's accessible name announces the linked state", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: yahooLeague() }} />,
    );
    // The linked (Yahoo) tab announces "..., league connected"; an unlinked tab
    // (ESPN here) keeps its bare label, so the two states are distinguishable.
    expect(
      screen.getByRole("tab", { name: /^yahoo, league connected$/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: /^yahoo$/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^espn$/i })).toBeInTheDocument();
  });

  it("an unconnected tab's accessible name is the bare label (no suffix)", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    // No linked league on the profile, so no tab carries the connected suffix.
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: /league connected/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps the connected dot aria-hidden so it is not double-announced", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null}
        activeProfile={{ ...activeProfile, linked_league: yahooLeague() }} />,
    );
    const dot = screen
      .getByRole("tab", { name: /^yahoo, league connected$/i })
      .querySelector("span.bg-green-500");
    expect(dot).not.toBeNull();
    expect(dot).toHaveAttribute("aria-hidden", "true");
  });

  it("exposes a labelled tablist containing role=tab for each platform", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByRole("tablist", { name: /fantasy platform/i })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(5);
  });

  it("aria-selected reflects the active tab and moves with it", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const sleeperTab = screen.getByRole("tab", { name: /^sleeper$/i });
    const espnTab = screen.getByRole("tab", { name: /^espn$/i });
    expect(sleeperTab).toHaveAttribute("aria-selected", "true");
    expect(espnTab).toHaveAttribute("aria-selected", "false");

    const u = userEvent.setup();
    await u.click(espnTab);
    expect(espnTab).toHaveAttribute("aria-selected", "true");
    expect(sleeperTab).toHaveAttribute("aria-selected", "false");
  });

  it("the panel is a tabpanel associated with the active tab", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("id", "linked-accounts-tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", "tab-sleeper");
    // Each tab points back at the panel it controls.
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toHaveAttribute(
      "aria-controls",
      "linked-accounts-tabpanel",
    );
  });

  it("uses a roving tabindex — only the active tab is in the tab order", () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    expect(screen.getByRole("tab", { name: /^sleeper$/i })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: /^espn$/i })).toHaveAttribute("tabindex", "-1");
  });

  it("ArrowRight moves focus and selection to the next tab", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const sleeperTab = screen.getByRole("tab", { name: /^sleeper$/i });
    const espnTab = screen.getByRole("tab", { name: /^espn$/i });
    sleeperTab.focus();
    const u = userEvent.setup();
    await u.keyboard("{ArrowRight}");
    expect(espnTab).toHaveFocus();
    expect(espnTab).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();
  });

  it("ArrowLeft wraps from the first tab to the last", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const sleeperTab = screen.getByRole("tab", { name: /^sleeper$/i });
    const cbsTab = screen.getByRole("tab", { name: /^cbs$/i });
    sleeperTab.focus();
    const u = userEvent.setup();
    await u.keyboard("{ArrowLeft}");
    expect(cbsTab).toHaveFocus();
    expect(cbsTab).toHaveAttribute("aria-selected", "true");
  });

  it("ArrowRight from the last tab wraps back to the first", async () => {
    render(
      <LinkedAccountsDialog open={true} onOpenChange={noop} user={baseUser}
        onRefresh={noop} initialError={null} activeProfile={activeProfile} />,
    );
    const sleeperTab = screen.getByRole("tab", { name: /^sleeper$/i });
    const cbsTab = screen.getByRole("tab", { name: /^cbs$/i });
    const u = userEvent.setup();
    await u.click(cbsTab);
    cbsTab.focus();
    await u.keyboard("{ArrowRight}");
    expect(sleeperTab).toHaveFocus();
    expect(sleeperTab).toHaveAttribute("aria-selected", "true");
  });
});
