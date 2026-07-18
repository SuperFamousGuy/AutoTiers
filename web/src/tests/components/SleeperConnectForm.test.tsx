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

  it("unwraps a raw JSON detail body from a connect ApiError instead of showing the blob", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([]);
    // `apiFetch` stores the raw response text as ApiError.message — here the
    // FastAPI JSON envelope for a Sleeper provider error.
    (connectSleeper as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(502, '{"detail":"Sleeper is unavailable right now. Try again shortly."}'),
    );
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Sleeper is unavailable right now. Try again shortly."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/^\{"detail"/)).not.toBeInTheDocument();
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

  it("'Link without a league' unwraps a raw JSON detail body on ApiError", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(502, '{"detail":"Sleeper is unavailable right now. Try again shortly."}'),
    );
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "leagueless");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() =>
      expect(screen.getByText(/no sleeper leagues found/i)).toBeInTheDocument(),
    );
    await u.click(screen.getByRole("button", { name: /link without a league/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Sleeper is unavailable right now. Try again shortly."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/^\{"detail"/)).not.toBeInTheDocument();
  });

  // --- Enter-to-submit (issue #641) ---

  it("Enter on the username step triggers Continue (not Connect) and advances", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: "L1", name: "Champs", season: 2026 }])
      .mockResolvedValueOnce([]);
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice{Enter}");
    // The visible (username) step's handler ran — leagues were looked up...
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    expect(listSleeperLeagues).toHaveBeenCalled();
    // ...and the not-yet-visible league step's handler did NOT fire.
    expect(connectSleeper).not.toHaveBeenCalled();
  });

  it("does not submit on Enter while the username is blank", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    render(<SleeperConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByLabelText(/sleeper username/i));
    await u.keyboard("{Enter}");
    expect(listSleeperLeagues).not.toHaveBeenCalled();
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
    // Import summary reflects the empty keepers_json / null adp_json on the fixture.
    expect(
      screen.getByText("No keepers detected · No ADP data for this league"),
    ).toBeInTheDocument();
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

  it("Refresh unwraps a raw JSON detail body from an ApiError", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (refreshLink as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(502, '{"detail":"Sleeper is unavailable right now. Try again shortly."}'),
    );
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() =>
      expect(
        screen.getByText("Sleeper is unavailable right now. Try again shortly."),
      ).toBeInTheDocument(),
    );
  });

  it("Disconnect confirms before calling disconnectLink, then calls onRefresh", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />,
    );
    const u = userEvent.setup();
    // First click only reveals the inline confirm — no network call yet (#787).
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    expect(disconnectLink).not.toHaveBeenCalled();
    // The destructive action gets focus so it's reachable without a Tab hunt.
    const confirm = screen.getByRole("button", { name: /^confirm disconnect$/i });
    expect(confirm).toHaveFocus();
    await u.click(confirm);
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Disconnect Cancel restores the plain row with no network call", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    await u.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(disconnectLink).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /disconnect sleeper/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^confirm disconnect$/i })).not.toBeInTheDocument();
  });

  it("Disconnect unwraps a raw JSON detail body from an ApiError", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (disconnectLink as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(409, '{"detail":"Couldn\'t unlink right now. Try again shortly."}'),
    );
    render(
      <SleeperConnectForm profile={sleeperLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />,
    );
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect sleeper/i }));
    await u.click(screen.getByRole("button", { name: /^confirm disconnect$/i }));
    await waitFor(() =>
      expect(screen.getByText("Couldn't unlink right now. Try again shortly.")).toBeInTheDocument(),
    );
  });
});
