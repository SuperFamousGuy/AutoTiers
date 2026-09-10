import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import type { PlayerSearchResult } from "@/api/types";

const sampleSearchResults: PlayerSearchResult[] = [
  { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
  { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF", espn_id: "3054212" },
];

const defaultBatch = vi.fn(async () => []);

describe("FavoritesPanel", () => {
  it("renders empty state for both sections", () => {
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText(/no favorite players yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no favorite teams yet/i)).toBeInTheDocument();
  });

  it("shows count badges", () => {
    render(
      <FavoritesPanel
        favoritePlayerIds={["1"]}
        favoriteTeams={["KC", "BUF"]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText("1 / 20")).toBeInTheDocument();
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("shows favorite players as persistent cards independent of search", async () => {
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
    ]);
    render(
      <FavoritesPanel
        favoritePlayerIds={["1"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /remove saquon barkley/i })).toBeInTheDocument()
    );
  });

  it("panel calls batchPlayers with unresolved ids on mount", async () => {
    const batch = vi.fn(async () => []);
    render(
      <FavoritesPanel
        favoritePlayerIds={["42", "99"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() => expect(batch).toHaveBeenCalledWith(["42", "99"]));
  });

  it("skeleton cards render while batchLoading is true", async () => {
    let resolveBatch!: (v: PlayerSearchResult[]) => void;
    const batch = vi.fn(
      () => new Promise<PlayerSearchResult[]>((res) => { resolveBatch = res; })
    );
    render(
      <FavoritesPanel
        favoritePlayerIds={["1"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    // While the promise is pending, an animate-pulse skeleton should be in the DOM
    await waitFor(() =>
      expect(document.querySelector(".animate-pulse")).toBeInTheDocument()
    );
    resolveBatch([]);
  });

  it("batchLoading clears when all favorites removed while fetch is in-flight", async () => {
    let resolveBatch!: (v: PlayerSearchResult[]) => void;
    const batch = vi.fn(
      () => new Promise<PlayerSearchResult[]>((res) => { resolveBatch = res; })
    );
    const { rerender } = render(
      <FavoritesPanel
        favoritePlayerIds={["1", "2"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    // Batch in-flight — batchLoading must be true
    await waitFor(() =>
      expect(screen.getByTestId("player-favorites")).toHaveAttribute("data-batchloading", "true")
    );
    // Remove all favorites while batch still pending
    rerender(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    // Cleanup must have cleared batchLoading
    await waitFor(() =>
      expect(screen.getByTestId("player-favorites")).toHaveAttribute("data-batchloading", "false")
    );
    resolveBatch([]);
  });

  it("after batch resolves, player names appear in cards", async () => {
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
    ]);
    render(
      <FavoritesPanel
        favoritePlayerIds={["1"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByText("Saquon Barkley")).toBeInTheDocument()
    );
  });

  it("unresolved ids fall back to showing raw id", async () => {
    const batch = vi.fn(async () => []);
    render(
      <FavoritesPanel
        favoritePlayerIds={["unknown-id"]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByText("unknown-id")).toBeInTheDocument()
    );
  });

  it("removing a card calls onTogglePlayer with that player's id", async () => {
    const onTogglePlayer = vi.fn();
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: null },
      { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF", espn_id: null },
    ]);
    render(
      <FavoritesPanel
        favoritePlayerIds={["1", "2"]}
        favoriteTeams={[]}
        onTogglePlayer={onTogglePlayer}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /remove saquon barkley/i })).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole("button", { name: /remove saquon barkley/i }));
    expect(onTogglePlayer).toHaveBeenCalledWith("1");
  });

  it("debounced search input triggers searchPlayers callback", async () => {
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    await waitFor(() => expect(search).toHaveBeenCalledWith("barkley"));
  });

  it("debounce coalesces rapid keystrokes into fewer calls", async () => {
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    await waitFor(() => expect(search).toHaveBeenCalled());
    expect(search.mock.calls.length).toBeLessThan("barkley".length);
  });

  it("shows a no-match empty state for a query with zero results", async () => {
    const search = vi.fn(async () => []);
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    await userEvent.type(screen.getByPlaceholderText(/search players/i), "zzz");
    expect(await screen.findByText(/no players match "zzz"/i)).toBeInTheDocument();
  });

  it("clicking Add invokes onTogglePlayer with the new player ID", async () => {
    const onTogglePlayer = vi.fn();
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={onTogglePlayer}
        onToggleTeam={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    const addButton = await screen.findByRole("button", { name: /add saquon barkley/i });
    await userEvent.click(addButton);
    expect(onTogglePlayer).toHaveBeenCalledWith("1");
  });

  it("at-cap disables Add", async () => {
    const tooManyPlayers = Array.from({ length: 20 }, (_, i) => `p${i}`);
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favoritePlayerIds={tooManyPlayers}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText("20 / 20")).toBeInTheDocument();
    expect(screen.getByText(/limit reached \(20 players\)/i)).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText(/search players/i), "barkley");
    const addButton = await screen.findByRole("button", { name: /add saquon barkley/i });
    expect(addButton).toBeDisabled();
  });

  it("cap-reached warnings use WCAG-AA amber classes in both themes (#1054)", () => {
    const tooManyPlayers = Array.from({ length: 20 }, (_, i) => `p${i}`);
    render(
      <FavoritesPanel
        favoritePlayerIds={tooManyPlayers}
        favoriteTeams={["KC", "BUF", "PHI", "SF"]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    // Count badges (amber-600 failed light mode) and "Limit reached" copy
    // (amber-700 failed the default dark mode) both move to a mode-aware pair
    // that clears 4.5:1 in each theme.
    const playerCount = screen.getByText("20 / 20");
    expect(playerCount.className).toContain("text-amber-800");
    expect(playerCount.className).toContain("dark:text-amber-500");
    const teamCount = screen.getByText("4 / 4");
    expect(teamCount.className).toContain("text-amber-800");
    expect(teamCount.className).toContain("dark:text-amber-500");
    const playerLimit = screen.getByText(/limit reached \(20 players\)/i);
    expect(playerLimit.className).toContain("text-amber-800");
    expect(playerLimit.className).toContain("dark:text-amber-500");
    const teamLimit = screen.getByText(/limit reached \(4 teams\)/i);
    expect(teamLimit.className).toContain("text-amber-800");
    expect(teamLimit.className).toContain("dark:text-amber-500");
    // The reported failing shades must be gone.
    for (const el of [playerCount, teamCount, playerLimit, teamLimit]) {
      expect(el.className).not.toMatch(/(?<!dark:)text-amber-600\b/);
      expect(el.className).not.toMatch(/(?<!dark:)text-amber-700\b/);
    }
  });

  it("team grid renders 32 teams with full-name aria-labels grouped by conference and division", () => {
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByRole("button", { name: "Kansas City Chiefs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buffalo Bills" })).toBeInTheDocument();
    // Conference headings
    expect(screen.getByText("AFC")).toBeInTheDocument();
    expect(screen.getByText("NFC")).toBeInTheDocument();
    // Division subheadings appear once per conference (2×4 = 8 total)
    expect(screen.getAllByText("East").length).toBe(2);
    expect(screen.getAllByText("West").length).toBe(2);
    const teamButtons = screen.getAllByRole("button", { pressed: false });
    expect(teamButtons.length).toBeGreaterThanOrEqual(32);
  });

  it("toggling a team calls onToggleTeam with the team code", async () => {
    const onToggleTeam = vi.fn();
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={[]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={onToggleTeam}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    const kc = screen.getByRole("button", { name: "Kansas City Chiefs" });
    await userEvent.click(kc);
    expect(onToggleTeam).toHaveBeenCalledWith("KC");
  });

  it("teams-at-cap disables unselected team buttons (unified disabled treatment)", () => {
    render(
      <FavoritesPanel
        favoritePlayerIds={[]}
        favoriteTeams={["KC", "BUF", "PHI", "SF"]}
        onTogglePlayer={vi.fn()}
        onToggleTeam={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByRole("button", { name: "Dallas Cowboys" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Kansas City Chiefs" })).not.toBeDisabled();
  });
});
