import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  connectEspn: vi.fn(),
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

const baseProfile: Profile = {
  id: "p1",
  name: "My",
  settings_json: {},
  rules_json: {},
  linked_league: null,
};

const espnLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "espn",
    league_id: "12345",
    league_metadata_json: { name: "ESPN Champs", season: 2026 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("EspnConnectForm", () => {
  it("connects public league without cookie fields", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<EspnConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345",
    })));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("Connect is disabled when league ID is empty in public mode", () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("Connect becomes enabled with cookies only in private mode (no league ID)", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeEnabled();
  });

  it("Connect stays disabled with a League ID + only SWID in private mode", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    // espn_s2 left blank — a half cookie pair must not be submittable.
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("Connect stays disabled with a League ID + only espn_s2 in private mode", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    // SWID left blank.
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("reveals SWID + espn_s2 fields when Private League button is clicked", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    expect(screen.queryByLabelText(/swid/i)).not.toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    expect(await screen.findByLabelText(/swid/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/espn_s2/i)).toBeInTheDocument();
  });

  it("includes cookies in the body when private + all fields filled", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345", swid: "{abc-123}", espn_s2: "blob",
    })));
  });

  // --- Enter-to-submit (issue #641) ---

  it("submits a public league on Enter from the League ID field", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<EspnConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345{Enter}");
    await waitFor(() =>
      expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({ league_id: "12345" })),
    );
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("does not submit on Enter while the Connect guard is unmet", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    // Public mode with empty League ID → Connect disabled → Enter is a no-op.
    await u.click(screen.getByLabelText(/league id/i));
    await u.keyboard("{Enter}");
    expect(connectEspn).not.toHaveBeenCalled();
  });

  it("Public/Private toggle buttons do not submit the form (type=button)", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    // Clicking a toggle must switch mode, never fire a connect.
    await u.click(screen.getByRole("button", { name: /^private league$/i }));
    await u.click(screen.getByRole("button", { name: /^public league$/i }));
    expect(connectEspn).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /^public league$/i })).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: /^private league$/i })).toHaveAttribute("type", "button");
  });

  // --- league visibility toggle accessibility ---

  it("announces the active mode to assistive tech via aria-pressed (Public by default)", () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    // Exactly one toggle is pressed, and it is the Public option on first render.
    const pressed = screen.getByRole("button", { pressed: true });
    expect(pressed).toHaveAccessibleName(/public league/i);
    expect(screen.getByRole("button", { name: /^private league$/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("groups the toggle under an accessible 'League visibility' label", () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByRole("group", { name: /league visibility/i })).toBeInTheDocument();
  });

  it("flips the pressed state when Private is chosen with the keyboard (Tab + Space)", async () => {
    render(<EspnConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    // Tab to the first toggle (Public), then to the second (Private), and activate with Space.
    await u.tab();
    expect(screen.getByRole("button", { name: /^public league$/i })).toHaveFocus();
    await u.tab();
    expect(screen.getByRole("button", { name: /^private league$/i })).toHaveFocus();
    await u.keyboard(" ");
    // Selection state moved to Private, and only one toggle is pressed.
    expect(screen.getByRole("button", { pressed: true })).toHaveAccessibleName(/private league/i);
    expect(screen.getByRole("button", { name: /^public league$/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  // --- connected state ---

  it("shows connected state card when profile.linked_league.provider === 'espn'", () => {
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    expect(screen.getByText(/connected!/i)).toBeInTheDocument();
    expect(screen.getByText("ESPN Champs")).toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });

  it("Refresh calls refreshLink then onRefresh", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Disconnect calls disconnectLink then onRefresh", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <EspnConnectForm profile={espnLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect espn/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
