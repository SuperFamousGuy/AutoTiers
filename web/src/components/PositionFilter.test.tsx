import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PositionFilter, POSITION_FILTER_OPTIONS } from "@/components/PositionFilter";

describe("PositionFilter", () => {
  it("renders one chip per canonical position, with 'ALL' labelled 'All'", () => {
    render(<PositionFilter value="ALL" onChange={vi.fn()} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(POSITION_FILTER_OPTIONS.length);
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "QB" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "DST" })).toBeInTheDocument();
  });

  it("calls onChange with the selected position", async () => {
    const onChange = vi.fn();
    render(<PositionFilter value="ALL" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "RB" }));
    expect(onChange).toHaveBeenCalledWith("RB");
  });

  it("gives every chip a >=40px mobile tap target that condenses to h-9 on sm+", () => {
    // Guards issue #578's live-draft mobile tap-target requirement (>=40px):
    // 40px tall on touch, denser 36px from the sm breakpoint up.
    render(<PositionFilter value="ALL" onChange={vi.fn()} />);
    for (const btn of screen.getAllByRole("button")) {
      expect(btn.className).toContain("h-10");
      expect(btn.className).toContain("sm:h-9");
    }
  });

  it("spaces chips 6px apart on mobile and restores 4px on sm+", () => {
    const { container } = render(<PositionFilter value="ALL" onChange={vi.fn()} />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).toHaveClass("gap-1.5");
    expect(wrapper).toHaveClass("sm:gap-1");
    // flex-wrap keeps all 7 chips from overflowing at narrow widths.
    expect(wrapper).toHaveClass("flex", "flex-wrap");
  });

  it("applies pointer-events-none to the active chip", () => {
    render(<PositionFilter value="QB" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "QB" }).className).toContain("pointer-events-none");
  });

  it("marks only the active chip aria-pressed for assistive tech (issue #661)", () => {
    render(<PositionFilter value="RB" onChange={vi.fn()} />);
    // The active option announces as pressed/selected to screen readers.
    expect(screen.getByRole("button", { name: "RB" })).toHaveAttribute("aria-pressed", "true");
    // Every other chip is explicitly not-pressed (never missing/undefined).
    for (const opt of POSITION_FILTER_OPTIONS.filter((o) => o !== "RB")) {
      const label = opt === "ALL" ? "All" : opt;
      expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("wraps the chips in a labelled group so the control set is discoverable", () => {
    render(<PositionFilter value="ALL" onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Filter by position" })).toBeInTheDocument();
  });
});
