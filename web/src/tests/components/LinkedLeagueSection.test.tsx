import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  refreshLink: vi.fn(),
  disconnectLink: vi.fn(),
}));

const profile: Profile = {
  id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null,
};

beforeEach(() => vi.clearAllMocks());

describe("LinkedLeagueSection", () => {
  it("when not linked, shows Connect Sleeper + ESPN buttons and coming-soon rows", () => {
    render(
      <LinkedLeagueSection
        profile={profile}
        onChanged={vi.fn()}
        onConnectSleeper={vi.fn()}
        onConnectEspn={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /connect sleeper/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect espn/i })).toBeInTheDocument();
    expect(screen.getByText(/nfl fantasy/i)).toBeInTheDocument();
    expect(screen.getByText(/cbs/i)).toBeInTheDocument();
    expect(screen.getAllByText(/coming soon/i)).toHaveLength(2);
  });

  it("Connect button invokes the parent callback (form rendered in the dialog)", async () => {
    const onConnectSleeper = vi.fn();
    const onConnectEspn = vi.fn();
    render(
      <LinkedLeagueSection
        profile={profile}
        onChanged={vi.fn()}
        onConnectSleeper={onConnectSleeper}
        onConnectEspn={onConnectEspn}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /connect sleeper/i }));
    expect(onConnectSleeper).toHaveBeenCalled();
    await u.click(screen.getByRole("button", { name: /connect espn/i }));
    expect(onConnectEspn).toHaveBeenCalled();
  });

  it("when linked, shows provider + league name + Refresh + Disconnect", () => {
    const linked = {
      ...profile,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "2026-01-01",
      },
    };
    render(
      <LinkedLeagueSection
        profile={linked}
        onChanged={vi.fn()}
        onConnectSleeper={vi.fn()}
        onConnectEspn={vi.fn()}
      />,
    );
    expect(screen.getByText(/PPR Champs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^refresh$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^disconnect$/i })).toBeInTheDocument();
  });

  it("disconnect calls API and onChanged", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onChanged = vi.fn();
    const linked = {
      ...profile,
      linked_league: {
        profile_id: "p1", provider: "sleeper" as const, league_id: "L1",
        league_metadata_json: { name: "PPR Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "2026-01-01",
      },
    };
    render(
      <LinkedLeagueSection
        profile={linked}
        onChanged={onChanged}
        onConnectSleeper={vi.fn()}
        onConnectEspn={vi.fn()}
      />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^disconnect$/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
