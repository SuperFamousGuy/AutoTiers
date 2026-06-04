import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";

describe("PlayerHeadshot", () => {
  it("renders an img element when espnId is non-null", () => {
    render(<PlayerHeadshot espnId="3918298" name="Ja'Marr Chase" />);
    const img = screen.getByRole("img", { name: "Ja'Marr Chase" });
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute(
      "src",
      "https://a.espncdn.com/i/headshots/nfl/players/full/3918298.png"
    );
  });

  it("renders silhouette div when espnId is null", () => {
    const { container } = render(<PlayerHeadshot espnId={null} name="Unknown" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    // aria-hidden div is present
    const silhouette = container.querySelector("[aria-hidden='true']");
    expect(silhouette).toBeInTheDocument();
  });

  it("swaps to silhouette div when image fires onError", () => {
    render(<PlayerHeadshot espnId="bad-id" name="Bad Player" />);
    const img = screen.getByRole("img", { name: "Bad Player" });
    fireEvent.error(img);
    // After error the img should no longer be in the DOM
    expect(screen.queryByRole("img", { name: "Bad Player" })).not.toBeInTheDocument();
    const { container } = render(<PlayerHeadshot espnId={null} name="Bad Player" />);
    expect(container.querySelector("[aria-hidden='true']")).toBeInTheDocument();
  });
});
