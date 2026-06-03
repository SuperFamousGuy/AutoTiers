import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesDialog } from "@/components/FavoritesDialog";
import * as favoritesApi from "@/api/favorites";
import * as useFavoritesModule from "@/hooks/useFavorites";

const emptyFavorites = { favorite_player_ids: [], favorite_teams: [] };

describe("FavoritesDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing visible when closed", () => {
    vi.spyOn(useFavoritesModule, "useFavorites").mockReturnValue({
      favorites: emptyFavorites,
      loading: false,
      error: null,
      save: vi.fn(),
    });
    const { queryByText } = render(
      <FavoritesDialog open={false} onOpenChange={vi.fn()} isLoggedIn={false} />
    );
    expect(queryByText("Favorites")).not.toBeInTheDocument();
  });

  it("renders dialog title and FavoritesPanel when open", () => {
    vi.spyOn(useFavoritesModule, "useFavorites").mockReturnValue({
      favorites: emptyFavorites,
      loading: false,
      error: null,
      save: vi.fn(),
    });
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);

    render(<FavoritesDialog open={true} onOpenChange={vi.fn()} isLoggedIn={true} />);

    expect(screen.getByText("Favorites")).toBeInTheDocument();
    expect(screen.getByText(/no favorite players yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no favorite teams yet/i)).toBeInTheDocument();
  });

  it("calls useFavorites with isLoggedIn value", () => {
    const spy = vi.spyOn(useFavoritesModule, "useFavorites").mockReturnValue({
      favorites: emptyFavorites,
      loading: false,
      error: null,
      save: vi.fn(),
    });
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);

    render(<FavoritesDialog open={true} onOpenChange={vi.fn()} isLoggedIn={true} />);

    expect(spy).toHaveBeenCalledWith(true);
  });

  it("calls useFavorites with false when not logged in", () => {
    const spy = vi.spyOn(useFavoritesModule, "useFavorites").mockReturnValue({
      favorites: emptyFavorites,
      loading: false,
      error: null,
      save: vi.fn(),
    });
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);

    render(<FavoritesDialog open={true} onOpenChange={vi.fn()} isLoggedIn={false} />);

    expect(spy).toHaveBeenCalledWith(false);
  });

  it("calls onOpenChange when dialog close is triggered", async () => {
    vi.spyOn(useFavoritesModule, "useFavorites").mockReturnValue({
      favorites: emptyFavorites,
      loading: false,
      error: null,
      save: vi.fn(),
    });
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);

    const onOpenChange = vi.fn();
    render(<FavoritesDialog open={true} onOpenChange={onOpenChange} isLoggedIn={false} />);

    const closeButton = screen.getByRole("button", { name: "" });
    await userEvent.click(closeButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
