import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinkedLeagueChip } from "@/components/LinkedLeagueChip";

vi.mock("@/api/linkedLeague", () => ({
  refreshLink: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("LinkedLeagueChip", () => {
  it("renders provider + league name and a Refresh button", () => {
    render(<LinkedLeagueChip profileId="p1" provider="sleeper" leagueName="PPR Champs" onRefreshed={vi.fn()} />);
    expect(screen.getByText(/auto-detected from sleeper/i)).toBeInTheDocument();
    expect(screen.getByText(/PPR Champs/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
  });

  it("clicking Refresh calls refreshLink and onRefreshed", async () => {
    const { refreshLink } = await import("@/api/linkedLeague");
    (refreshLink as ReturnType<typeof vi.fn>).mockResolvedValueOnce({});
    const onRefreshed = vi.fn();
    render(<LinkedLeagueChip profileId="p1" provider="sleeper" leagueName="PPR Champs" onRefreshed={onRefreshed} />);
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /refresh/i }));
    await waitFor(() => expect(refreshLink).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onRefreshed).toHaveBeenCalled());
  });
});
