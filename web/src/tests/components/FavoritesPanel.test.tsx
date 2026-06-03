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
  { id: "1", name: "Saquon Barkley", position: "RB", team: "PHI" },
  { id: "2", name: "Christian McCaffrey", position: "RB", team: "SF" },
];

describe("FavoritesPanel", () => {
  it("renders empty state for both sections", () => {
    render(
      <FavoritesPanel
        favorites={makeFav()}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => [])}
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
      />
    );
    expect(screen.getByText("1 / 20")).toBeInTheDocument();
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("search input triggers searchPlayers callback", async () => {
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel favorites={makeFav()} onSave={vi.fn()} searchPlayers={search} />
    );
    const input = screen.getByPlaceholderText(/search players/i);
    await userEvent.type(input, "barkley");
    await waitFor(() => expect(search).toHaveBeenCalledWith("barkley"));
  });

  it("clicking Add invokes onSave with the new player ID", async () => {
    const onSave = vi.fn(async () => {});
    const search = vi.fn(async () => sampleSearchResults);
    render(
      <FavoritesPanel favorites={makeFav()} onSave={onSave} searchPlayers={search} />
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

  it("at-cap disables Add and shows tooltip text", () => {
    const tooManyPlayers = Array.from({ length: 20 }, (_, i) => String(i));
    render(
      <FavoritesPanel
        favorites={makeFav({ favorite_player_ids: tooManyPlayers })}
        onSave={vi.fn()}
        searchPlayers={vi.fn(async () => sampleSearchResults)}
      />
    );
    expect(screen.getByText("20 / 20")).toBeInTheDocument();
    expect(screen.getByText(/limit reached/i)).toBeInTheDocument();
  });

  it("team grid renders 32 teams", () => {
    render(
      <FavoritesPanel favorites={makeFav()} onSave={vi.fn()} searchPlayers={vi.fn(async () => [])} />
    );
    expect(screen.getAllByRole("button", { name: /^team-/i })).toHaveLength(32);
  });

  it("toggling a team calls onSave with the team added", async () => {
    const onSave = vi.fn(async () => {});
    render(
      <FavoritesPanel favorites={makeFav()} onSave={onSave} searchPlayers={vi.fn(async () => [])} />
    );
    const kc = screen.getByRole("button", { name: "team-KC" });
    await userEvent.click(kc);
    expect(onSave).toHaveBeenCalledWith({
      favorite_player_ids: [],
      favorite_teams: ["KC"],
    });
  });
});
