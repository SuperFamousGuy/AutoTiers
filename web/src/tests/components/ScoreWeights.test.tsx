import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreWeights } from "@/components/ScoreWeights";
import type { Weights } from "@/lib/weights";

describe("ScoreWeights", () => {
  it("renders both weight values as percentages", () => {
    const weights: Weights = { prior: 40, consensus: 60 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("shows the sum and a 'sums 100%' indicator", () => {
    const weights: Weights = { prior: 40, consensus: 60 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/sums.*100/i)).toBeInTheDocument();
  });

  it("calls onChange with redistributed weights when a slider is adjusted", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 40, consensus: 60 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    const user = userEvent.setup();
    await user.keyboard("{ArrowRight>10}");

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior + lastCall.consensus).toBe(100);
  });
});
