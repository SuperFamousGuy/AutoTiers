import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Logo } from "@/components/Logo";

describe("Logo", () => {
  it("renders the AutoTiers wordmark by default", () => {
    render(<Logo />);
    expect(screen.getByText("AutoTiers")).toBeInTheDocument();
  });

  it("renders the tier-ladder mark as decorative (aria-hidden)", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    // three ascending bars
    expect(svg!.querySelectorAll("rect")).toHaveLength(3);
  });

  it("drives the mark color from the brand primary token", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveClass("text-primary");
    expect(svg).toHaveAttribute("fill", "currentColor");
  });

  it("hides the wordmark when showWordmark is false", () => {
    render(<Logo showWordmark={false} />);
    expect(screen.queryByText("AutoTiers")).not.toBeInTheDocument();
  });

  it("merges a caller-supplied className onto the wrapper", () => {
    const { container } = render(<Logo className="h-full" />);
    expect(container.firstChild).toHaveClass("h-full");
    expect(container.firstChild).toHaveClass("inline-flex");
  });
});
