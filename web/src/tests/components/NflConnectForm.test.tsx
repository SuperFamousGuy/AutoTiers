import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NflConnectForm } from "@/components/NflConnectForm";
import { ApiError } from "@/api/client";
import type { Profile } from "@/api/types";

vi.mock("@/api/linkedLeague", () => ({
  connectNfl: vi.fn(),
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

const nflLinkedProfile: Profile = {
  ...baseProfile,
  linked_league: {
    profile_id: "p1",
    provider: "nfl",
    league_id: "55555",
    league_metadata_json: { name: "NFL Champs", season: 2025 },
    keepers_json: [],
    adp_json: null,
    last_synced_at: "2026-06-01T00:00:00Z",
  },
};

describe("NflConnectForm", () => {
  it("Connect is disabled until League ID is filled (season pre-fills)", async () => {
    render(<NflConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    const connect = screen.getByRole("button", { name: /connect nfl/i });
    expect(connect).toBeDisabled();
    await u.type(screen.getByLabelText("League ID"), "55555");
    expect(connect).toBeEnabled();
  });

  it("Connect is disabled when season is blanked out", async () => {
    render(<NflConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("League ID"), "55555");
    await u.clear(screen.getByLabelText("Season"));
    expect(screen.getByRole("button", { name: /connect nfl/i })).toBeDisabled();
  });

  it("Connect is disabled for whitespace-only League ID", async () => {
    render(<NflConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("League ID"), "   ");
    expect(screen.getByRole("button", { name: /connect nfl/i })).toBeDisabled();
  });

  it("submits trimmed league_id and numeric season, calls onLinked", async () => {
    const { connectNfl } = await import("@/api/linkedLeague");
    (connectNfl as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: nflLinkedProfile.linked_league,
      profile: nflLinkedProfile,
    });
    const onLinked = vi.fn();
    render(<NflConnectForm profile={baseProfile} onLinked={onLinked} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("League ID"), "  55555  ");
    await u.clear(screen.getByLabelText("Season"));
    await u.type(screen.getByLabelText("Season"), "2025");
    await u.click(screen.getByRole("button", { name: /connect nfl/i }));
    await waitFor(() => expect(connectNfl).toHaveBeenCalledWith("p1", {
      league_id: "55555",
      season: 2025,
    }));
    expect(onLinked).toHaveBeenCalled();
  });

  it("surfaces the backend error message verbatim on ApiError", async () => {
    const { connectNfl } = await import("@/api/linkedLeague");
    (connectNfl as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(404, "NFL.com couldn't find league 999 for 2025. Check the League ID and season."),
    );
    render(<NflConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("League ID"), "999");
    await u.click(screen.getByRole("button", { name: /connect nfl/i }));
    await waitFor(() =>
      expect(screen.getByText(/couldn't find league 999/i)).toBeInTheDocument(),
    );
  });

  it("renders the connected state (no inputs) when provider is nfl", () => {
    render(<NflConnectForm profile={nflLinkedProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText("Connected!")).toBeInTheDocument();
    expect(screen.getByText("NFL Champs")).toBeInTheDocument();
    expect(screen.getByText(/NFL Fantasy · 2025/)).toBeInTheDocument();
    expect(screen.queryByLabelText("League ID")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /disconnect nfl/i })).toBeInTheDocument();
  });

  it("does not render a credential/login field (no NFL.com login is collected)", () => {
    render(<NflConnectForm profile={baseProfile} onLinked={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.getByText(/No NFL.com login needed/i)).toBeInTheDocument();
  });
});
