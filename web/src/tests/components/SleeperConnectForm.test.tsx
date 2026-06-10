import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
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

const sleeperLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "sleeper",
    league_id: "L1",
    league_metadata_json: { name: "Best League", season: 2026 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("SleeperConnectForm", () => {
  // --- connect flow ---

  it("lists leagues across current + previous season, then connects on confirm", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([{ id: "L0", name: "Old Dynasty", season: 2025 }]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L1",
        league_metadata_json: { name: "Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    expect(screen.getByText(/old dynasty/i)).toBeInTheDocument();
    expect(listSleeperLeagues).toHaveBeenCalledTimes(2);
    await u.selectOptions(screen.getByLabelText(/select your league/i), "L1");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L1", season: 2026,
    }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("connects with the SELECTED league's season, not always the current one", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: "L0", name: "Old Dynasty", season: 2025 }]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L0",
        league_metadata_json: { name: "Old Dynasty", season: 2025 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/old dynasty/i)).toBeInTheDocument());
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L0", season: 2025,
    }));
  });

  it("shows error when username not found", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new ApiError(404, "not found"))
      .mockRejectedValueOnce(new ApiError(404, "not found"));
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "ghost");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/couldn't find/i)).toBeInTheDocument());
  });

  it("upfront username step does NOT show the link-without-league button", () => {
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /link without a league/i })).not.toBeInTheDocument();
  });

  it("when zero leagues are found, surfaces a 'Link without a league' button that pre-links", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: null,
        league_metadata_json: null, keepers_json: null, adp_json: null, last_synced_at: "x" },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "leagueless");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() =>
      expect(screen.getByText(/no sleeper leagues found/i)).toBeInTheDocument(),
    );
    await u.click(screen.getByRole("button", { name: /link without a league/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", { username: "leagueless" }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  // --- step indicator ---

  it("shows a step indicator on the username step", () => {
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByLabelText(/connection steps/i)).toBeInTheDocument();
  });

  it("'Wrong username?' link goes back to step 1 without clearing the username field", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([]);
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    await u.click(screen.getByText(/wrong username/i));
    const input = screen.getByLabelText(/sleeper username/i) as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("alice");
  });

  // --- connected state ---

  it("shows connected state card when profile.linked_league.provider === 'sleeper'", () => {
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    expect(screen.getByText(/connected!/i)).toBeInTheDocument();
    expect(screen.getByText("Best League")).toBeInTheDocument();
    expect(screen.queryByLabelText(/sleeper username/i)).not.toBeInTheDocument();
  });

  it("Refresh calls refreshLink then onRefresh", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
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
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });
});
