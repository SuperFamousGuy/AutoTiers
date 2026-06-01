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
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

const baseUser: User = {
  id: "u1",
  email: "alice@example.com",
  yahoo_subject: null,
  google_subject: null,
  last_active_profile_id: null,
};

const noop = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LinkedAccountsDialog", () => {
  it("renders email and shows both providers as not connected", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getAllByRole("button", { name: /^connect$/i })).toHaveLength(2);
  });

  it("shows Disconnect when a provider is connected", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByRole("button", { name: /disconnect google/i })).toBeInTheDocument();
  });

  it("Disconnect calls unlinkGoogle then refresh", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const refresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={refresh}
        initialError={null}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    await waitFor(() => expect(unlinkGoogle).toHaveBeenCalled());
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("shows the API error message when Disconnect fails", async () => {
    const { unlinkGoogle } = await import("@/api/auth");
    const { ApiError } = await import("@/api/client");
    (unlinkGoogle as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "Cannot unlink last sign-in method"),
    );
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={{ ...baseUser, google_subject: "g-sub" }}
        onRefresh={noop}
        initialError={null}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect google/i }));
    expect(await screen.findByText(/last sign-in method/i)).toBeInTheDocument();
  });

  it("Connect Google navigates to the authorize URL with intent=link", async () => {
    const originalHref = window.location.href;
    // jsdom's window.location.href is settable; stub via a property descriptor.
    let assignedHref = "";
    const hrefSetter = vi.fn((v: string) => { assignedHref = v; });
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, set href(v: string) { hrefSetter(v); } },
    });
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError={null}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getAllByRole("button", { name: /^connect$/i })[0]);
    expect(assignedHref).toContain("/api/auth/google/authorize");
    expect(assignedHref).toContain("intent=link");
    // Restore (best-effort — jsdom's location is read-only by default).
    Object.defineProperty(window, "location", { writable: true, value: { href: originalHref } });
  });

  it("renders an initial error when provided", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError="This Google account is already linked to a different AutoTiers account."
      />,
    );
    expect(screen.getByText(/already linked/i)).toBeInTheDocument();
  });

  const activeProfile: Profile = {
    id: "p1",
    name: "My",
    settings_json: {},
    rules_json: [],
    linked_league: null,
  };

  it("shows 'Select a profile' fallback when no active profile and no league section", () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={noop}
        initialError={null}
      />,
    );
    expect(screen.getByText(/select a profile/i)).toBeInTheDocument();
  });

  it("clicking 'Connect Sleeper' hides Google/Yahoo and shows the Sleeper sub-form", async () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /connect sleeper/i }));
    // Sub-form input is the only signal it's mounted.
    expect(await screen.findByLabelText(/sleeper username/i)).toBeInTheDocument();
    // The Google/Yahoo provider rows are gone while the form is up.
    expect(screen.queryByText(/^Google$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Yahoo$/)).not.toBeInTheDocument();
  });

  it("clicking 'Connect ESPN' hides Google/Yahoo and shows the ESPN sub-form", async () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /connect espn/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Google$/)).not.toBeInTheDocument();
  });

  it("Cancel from the Sleeper sub-form returns to the provider list", async () => {
    render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={noop}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /connect sleeper/i }));
    await u.click(screen.getByRole("button", { name: /^cancel$/i }));
    // Provider list is back.
    expect(await screen.findByText(/^Google$/)).toBeInTheDocument();
  });

  it("closing the dialog resets active sub-form state", async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={onOpenChange}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /connect espn/i }));
    expect(await screen.findByLabelText(/league id/i)).toBeInTheDocument();

    // Close + reopen the dialog
    rerender(
      <LinkedAccountsDialog
        open={false}
        onOpenChange={onOpenChange}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    rerender(
      <LinkedAccountsDialog
        open={true}
        onOpenChange={onOpenChange}
        user={baseUser}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        initialError={null}
        activeProfile={activeProfile}
      />,
    );
    // Provider list is showing again, not the ESPN form.
    expect(await screen.findByText(/^Google$/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });
});
