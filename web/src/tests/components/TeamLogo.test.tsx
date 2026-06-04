import { describe, it, expect } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { TeamLogo } from "@/components/TeamLogo";

describe("TeamLogo", () => {
  it("renders an img with aria-hidden when not failed", () => {
    const { container } = render(<TeamLogo code="KC" />);
    const img = container.querySelector("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("aria-hidden", "true");
    expect(img).toHaveAttribute(
      "src",
      "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png"
    );
  });

  it("uses the size prop for width and height", () => {
    const { container } = render(<TeamLogo code="BUF" size={32} />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("width", "32");
    expect(img).toHaveAttribute("height", "32");
  });

  it("swaps to text code span when onError fires", () => {
    const { container, getByText } = render(<TeamLogo code="KC" />);
    const img = container.querySelector("img");
    expect(img).toBeInTheDocument();
    fireEvent.error(img!);
    // img gone, span with code appears
    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(getByText("KC")).toBeInTheDocument();
  });
});
