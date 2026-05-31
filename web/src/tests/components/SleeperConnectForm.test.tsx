import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";

vi.mock("@/api/linkedLeague", () => ({
  listSleeperLeagues: vi.fn(),
  connectSleeper: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("SleeperConnectForm", () => {
  it("lists leagues after submitting username, then connects on confirm", async () => {
    const { listSleeperLeagues, connectSleeper } = await import("@/api/linkedLeague");
    (listSleeperLeagues as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: "L1", name: "Champs", season: 2026 },
      { id: "L2", name: "Dynasty", season: 2026 },
    ]);
    (connectSleeper as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "sleeper", league_id: "L1",
        league_metadata_json: { name: "Champs", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    const onLinked = vi.fn();
    render(<SleeperConnectForm profileId="p1" onLinked={onLinked} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "alice");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/champs/i)).toBeInTheDocument());
    await u.selectOptions(screen.getByLabelText(/select your league/i), "L1");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectSleeper).toHaveBeenCalledWith("p1", {
      username: "alice", league_id: "L1", season: expect.any(Number),
    }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("shows error when username not found", async () => {
    const { listSleeperLeagues } = await import("@/api/linkedLeague");
    const { ApiError } = await import("@/api/client");
    (listSleeperLeagues as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new ApiError(404, "not found"));
    render(<SleeperConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/sleeper username/i), "ghost");
    await u.click(screen.getByRole("button", { name: /^continue$/i }));
    await waitFor(() => expect(screen.getByText(/not found|couldn't find/i)).toBeInTheDocument());
  });
});
