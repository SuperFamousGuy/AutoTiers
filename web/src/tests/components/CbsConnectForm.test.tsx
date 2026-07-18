import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CbsConnectForm } from "@/components/CbsConnectForm";
import { ApiError } from "@/api/client";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  connectCbs: vi.fn(),
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

const cbsLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "cbs",
    league_id: "999999",
    league_metadata_json: { name: "CBS Champs", season: 2026 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("CbsConnectForm", () => {
  it("Connect is disabled until email, password, and league ID are all filled", async () => {
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();

    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();

    await u.type(screen.getByLabelText(/cbs password/i), "hunter2");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();

    await u.type(screen.getByLabelText(/league id/i), "999999");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeEnabled();
  });

  it("Connect stays disabled when fields are whitespace-only", async () => {
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "   ");
    await u.type(screen.getByLabelText(/cbs password/i), "   ");
    await u.type(screen.getByLabelText(/league id/i), "   ");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("password field has type=password so it is masked and never echoed in plaintext markup", () => {
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByLabelText(/cbs password/i)).toHaveAttribute("type", "password");
  });

  it("email field has type=email", () => {
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByLabelText(/cbs email/i)).toHaveAttribute("type", "email");
  });

  it("calls connectCbs with trimmed email/password/league_id and surfaces the result via onLinked", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    (connectCbs as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: {
        profile_id: "p1", provider: "cbs", league_id: "999999",
        league_metadata_json: { name: "CBS Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x",
      },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<CbsConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "  fan@example.com  ");
    await u.type(screen.getByLabelText(/cbs password/i), "  hunter2  ");
    await u.type(screen.getByLabelText(/league id/i), "  999999  ");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));

    await waitFor(() =>
      expect(connectCbs).toHaveBeenCalledWith("p1", {
        email: "fan@example.com",
        password: "hunter2",
        league_id: "999999",
      }),
    );
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("renders the backend's error message verbatim via ApiError, not a hand-crafted guess", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    (connectCbs as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "CBS rejected your email or password — check both and try again."),
    );
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    await u.type(screen.getByLabelText(/cbs password/i), "wrong");
    await u.type(screen.getByLabelText(/league id/i), "999999");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));

    expect(
      await screen.findByText("CBS rejected your email or password — check both and try again."),
    ).toBeInTheDocument();
  });

  it("announces the connect failure to assistive tech via role=alert", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    (connectCbs as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, "CBS rejected your email or password — check both and try again."),
    );
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    // No alert exists before the form fails.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    await u.type(screen.getByLabelText(/cbs password/i), "wrong");
    await u.type(screen.getByLabelText(/league id/i), "999999");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "CBS rejected your email or password — check both and try again.",
    );
  });

  it("unwraps a raw JSON detail body from an ApiError instead of showing the blob", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    // `apiFetch` stores the raw response text as ApiError.message — here the
    // FastAPI JSON envelope for a CBS auth failure.
    (connectCbs as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(
        400,
        '{"detail":"CBS rejected your email or password — check both and try again."}',
      ),
    );
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    await u.type(screen.getByLabelText(/cbs password/i), "wrong");
    await u.type(screen.getByLabelText(/league id/i), "999999");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));

    expect(
      await screen.findByText("CBS rejected your email or password — check both and try again."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^\{"detail"/)).not.toBeInTheDocument();
  });

  it("falls back to a generic message when the rejected error is not an ApiError", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    (connectCbs as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("network down"));
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    await u.type(screen.getByLabelText(/cbs password/i), "hunter2");
    await u.type(screen.getByLabelText(/league id/i), "999999");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));

    expect(await screen.findByText(/connect failed/i)).toBeInTheDocument();
  });

  // --- Enter-to-submit (issue #641) ---

  it("submits on Enter from an input once all required fields are filled", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    (connectCbs as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: {
        profile_id: "p1", provider: "cbs", league_id: "999999",
        league_metadata_json: { name: "CBS Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x",
      },
      profile: baseProfile,
    });
    const onLinked = vi.fn();
    render(<CbsConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com");
    await u.type(screen.getByLabelText(/cbs password/i), "hunter2");
    // Enter from the last field submits the form — no mouse click on Connect.
    await u.type(screen.getByLabelText(/league id/i), "999999{Enter}");
    await waitFor(() =>
      expect(connectCbs).toHaveBeenCalledWith("p1", {
        email: "fan@example.com",
        password: "hunter2",
        league_id: "999999",
      }),
    );
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("does not submit on Enter while the Connect guard is unmet", async () => {
    const { connectCbs } = await import("@/api/linkedLeague");
    render(<CbsConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    // Only the email is filled; password + league ID missing, so Connect is disabled.
    await u.type(screen.getByLabelText(/cbs email/i), "fan@example.com{Enter}");
    expect(connectCbs).not.toHaveBeenCalled();
  });

  // --- connected state ---

  it("shows connected state card when profile.linked_league.provider === 'cbs'", () => {
    render(<CbsConnectForm profile={cbsLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText(/connected!/i)).toBeInTheDocument();
    expect(screen.getByText("CBS Champs")).toBeInTheDocument();
    // Import summary reflects the empty keepers_json / null adp_json on the fixture.
    expect(
      screen.getByText("No keepers detected · No ADP data for this league"),
    ).toBeInTheDocument();
    // No password field ever renders in the connected state.
    expect(screen.queryByLabelText(/cbs password/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/league id/i)).not.toBeInTheDocument();
  });

  it("Refresh calls refreshLink then onRefresh", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(<CbsConnectForm profile={cbsLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Refresh unwraps a raw JSON detail body from an ApiError", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(400, '{"detail":"CBS refused the refresh. Reconnect your account."}'),
    );
    render(<CbsConnectForm profile={cbsLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^refresh$/i }));
    await waitFor(() =>
      expect(screen.getByText("CBS refused the refresh. Reconnect your account.")).toBeInTheDocument(),
    );
  });

  it("Disconnect calls disconnectLink then onRefresh", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined);
    render(<CbsConnectForm profile={cbsLinkedProfile} onLinked={vi.fn()} onRefresh={onRefresh} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect cbs/i }));
    await waitFor(() => expect(disconnectLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it("Disconnect unwraps a raw JSON detail body from an ApiError", async () => {
    const { disconnectLink } = await import("@/api/linkedLeague");
    (disconnectLink as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(409, '{"detail":"Couldn\'t unlink right now. Try again shortly."}'),
    );
    render(<CbsConnectForm profile={cbsLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /disconnect cbs/i }));
    await waitFor(() =>
      expect(screen.getByText("Couldn't unlink right now. Try again shortly.")).toBeInTheDocument(),
    );
  });

  it("Refresh button is hidden when linked.league_id is not set", () => {
    const profileNoLeague: Profile = {
      ...baseProfile,
      linked_league: {
        profile_id: "p1",
        provider: "cbs",
        league_id: null,
        league_metadata_json: null,
        keepers_json: null,
        adp_json: null,
        last_synced_at: "2026-06-01T00:00:00Z",
      },
    };
    render(<CbsConnectForm profile={profileNoLeague} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /^refresh$/i })).not.toBeInTheDocument();
    // Disconnect is always shown regardless of league_id.
    expect(screen.getByRole("button", { name: /disconnect cbs/i })).toBeInTheDocument();
  });
});
