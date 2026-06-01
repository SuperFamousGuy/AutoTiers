import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EspnConnectForm } from "@/components/EspnConnectForm";

vi.mock("@/api/linkedLeague", () => ({
  connectEspn: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("EspnConnectForm", () => {
  it("connects public league without cookie fields", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    const onLinked = vi.fn();
    render(<EspnConnectForm profileId="p1" onLinked={onLinked} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345",
    })));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
  });

  it("Connect is disabled when neither a league ID nor cookies are filled", () => {
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  });

  it("Connect becomes enabled with cookies only (no league)", async () => {
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.click(screen.getByLabelText(/private league/i));
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    expect(screen.getByRole("button", { name: /^connect$/i })).toBeEnabled();
  });

  it("reveals SWID + espn_s2 fields when Private toggle is on", async () => {
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    expect(screen.queryByLabelText(/swid/i)).not.toBeInTheDocument();
    await u.click(screen.getByLabelText(/private league/i));
    expect(await screen.findByLabelText(/swid/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/espn_s2/i)).toBeInTheDocument();
  });

  it("includes cookies in the body when private + filled", async () => {
    const { connectEspn } = await import("@/api/linkedLeague");
    (connectEspn as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      linked_league: { profile_id: "p1", provider: "espn", league_id: "12345",
        league_metadata_json: { name: "X", season: 2026 },
        keepers_json: [], adp_json: null, last_synced_at: "x" },
      profile: { id: "p1", name: "My", settings_json: {}, rules_json: [], linked_league: null },
    });
    render(<EspnConnectForm profileId="p1" onLinked={vi.fn()} onCancel={vi.fn()} />);
    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/league id/i), "12345");
    await u.click(screen.getByLabelText(/private league/i));
    await u.type(screen.getByLabelText(/swid/i), "{{abc-123}");
    await u.type(screen.getByLabelText(/espn_s2/i), "blob");
    await u.click(screen.getByRole("button", { name: /^connect$/i }));
    await waitFor(() => expect(connectEspn).toHaveBeenCalledWith("p1", expect.objectContaining({
      league_id: "12345", swid: "{abc-123}", espn_s2: "blob",
    })));
  });
});
