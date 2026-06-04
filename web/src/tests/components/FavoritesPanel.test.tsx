import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import type { FavoritesOut, PlayerSearchResult } from "@/api/types";

const makeFav = (overrides: Partial<FavoritesOut> = {}): FavoritesOut => ({
  favorite_player_ids: [],
  favorite_teams: [],
  ...overrides,
});

const sampleSearchResults: PlayerSearchResult[] = [
  { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
  { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF", espn_id: "3054212" },
];

const defaultBatch = vi.fn(async () => []);

describe("FavoritesPanel", () => {
  it("renders empty state for both sections", () => {
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={vi.fn()}
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
        favorites={makeFav({ favorite_player_ids: ["1"], favorite_teams: ["KC", "BUF"] })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText("1 / 20")).toBeInTheDocument();
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("renders a loading spinner while loading", () => {
    render(
      <FavoritesPanel
        favorites={makeFav()}
        loading
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText(/loading favorites/i)).toBeInTheDocument();
    expect(screen.queryByText(/favorite players/i)).not.toBeInTheDocument();
  });

  it("renders an inline error with a working retry button", async () => {
    const onRetry = vi.fn();
    render(
      <FavoritesPanel
        favorites={makeFav()}
        error="Failed to load favorites"
        onRetry={onRetry}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByText(/failed to load favorites/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows favorite players as persistent cards independent of search", async () => {
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
    ]);
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: ["1"] })}
        onSave={vi.fn()}
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
        favorites={makeFav({ favorite_player_ids: ["42", "99"] })}
        onSave={vi.fn()}
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
        favorites={makeFav({ favorite_player_ids: ["1"] })}
        onSave={vi.fn()}
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

  it("after batch resolves, player names appear in cards", async () => {
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: "3054211" },
    ]);
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: ["1"] })}
        onSave={vi.fn()}
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
        favorites={makeFav({ favorite_player_ids: ["unknown-id"] })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByText("unknown-id")).toBeInTheDocument()
    );
  });

  it("removing a card calls onSave without that player", async () => {
    const onSave = vi.fn(async () => {});
    const batch = vi.fn(async () => [
      { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI", espn_id: null },
      { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF", espn_id: null },
    ]);
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: ["1", "2"] })}
        onSave={onSave}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={batch}
      />
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /remove saquon barkley/i })).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole("button", { name: /remove saquon barkley/i }));
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: ["2"],
      favorite_teams: [],
    });
  });

  it("debounced search input triggers searchPlayers callback", async () => {
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={vi.fn()}
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
        favorites={makeFav()}
        onSave={vi.fn()}
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
        favorites={makeFav()}
        onSave={vi.fn()}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    await userEvent.type(screen.getByPlaceholderText(/search players/i), "zzz");
    expect(await screen.findByText(/no players match "zzz"/i)).toBeInTheDocument();
  });

  it("clicking Add invokes onSave with the new player ID", async () => {
    const onSave = vi.fn(async () => {});
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={onSave}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    const addButton = await screen.findByRole("button", { name: /add saquon barkley/i });
    await userEvent.click(addButton);
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: ["1"],
      favorite_teams: [],
    });
  });

  it("shows a save-revert message when onSave rejects", async () => {
    const onSave = vi.fn(async () => {
      throw new Error("server down");
    });
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={onSave}
        searchPlayers={search}
        batchPlayers={defaultBatch}
      />
    );
    await userEvent.type(screen.getByPlaceholderText(/search players/i), "barkley");
    const addButton = await screen.findByRole("button", { name: /add saquon barkley/i });
    await userEvent.click(addButton);
    expect(await screen.findByRole("alert")).toHaveTextContent(/reverted/i);
  });

  it("at-cap disables Add and shows tooltip text", async () => {
    const tooManyPlayers = Array.from({ length: 20 }, (_, i) => `p${i}`);
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: tooManyPlayers })}
        onSave={vi.fn()}
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

  it("team grid renders 32 teams with full-name aria-labels grouped by conference and division", () => {
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={vi.fn()}
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

  it("toggling a team calls onSave with the team added", async () => {
    const onSave = vi.fn(async () => {});
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={onSave}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    const kc = screen.getByRole("button", { name: "Kansas City Chiefs" });
    await userEvent.click(kc);
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: [],
      favorite_teams: ["KC"],
    });
  });

  it("teams-at-cap disables unselected team buttons (unified disabled treatment)", () => {
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_teams: ["KC", "BUF", "PHI", "SF"] })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
        batchPlayers={defaultBatch}
      />
    );
    expect(screen.getByRole("button", { name: "Dallas Cowboys" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Kansas City Chiefs" })).not.toBeDisabled();
  });
});
