import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesDialog } from "@/components/FavoritesDialog";
import * as favoritesApi from "@/api/favorites";

describe("FavoritesDialog", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing visible when closed", () => {
    const { queryByText } = render(
      <FavoritesDialog open={false} onOpenChange={vi.fn()} />
    );
    expect(queryByText("Favorites")).not.toBeInTheDocument();
  });

  it("renders dialog title and FavoritesPanel (backed by localStorage) when open", () => {
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);
    vi.spyOn(favoritesApi, "batchPlayers").mockResolvedValue([]);

    render(<FavoritesDialog open={true} onOpenChange={vi.fn()} />);

    expect(screen.getByText("Favorites")).toBeInTheDocument();
    expect(screen.getByText(/no favorite players yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no favorite teams yet/i)).toBeInTheDocument();
  });

  it("calls onOpenChange when dialog close is triggered", async () => {
    vi.spyOn(favoritesApi, "searchPlayers").mockResolvedValue([]);
    vi.spyOn(favoritesApi, "batchPlayers").mockResolvedValue([]);

    const onOpenChange = vi.fn();
    render(<FavoritesDialog open={true} onOpenChange={onOpenChange} />);

    const closeButton = screen.getByRole("button", { name: "" });
    await userEvent.click(closeButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
