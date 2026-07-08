import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreWeights } from "@/components/ScoreWeights";
import type { Weights } from "@/lib/weights";

describe("ScoreWeights", () => {
  it("renders both weight values as percentages", () => {
    const weights: Weights = { prior: 30, consensus: 70 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByDisplayValue("30")).toBeInTheDocument();
    expect(screen.getByDisplayValue("70")).toBeInTheDocument();
  });

  it("shows the 'sums 100%' indicator when valid", () => {
    const weights: Weights = { prior: 30, consensus: 70 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/sums 100/i)).toBeInTheDocument();
  });

  it("shows an invalid-sum message when weights don't add to 100", () => {
    const weights: Weights = { prior: 30, consensus: 60 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/90/)).toBeInTheDocument();
    expect(screen.getByText(/adjust to total 100/i)).toBeInTheDocument();
  });

  it("auto-complements the other weight when a slider is adjusted", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 70 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    const user = userEvent.setup();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBe(31);
    expect(lastCall.consensus).toBe(69); // complemented so the pair still sums to 100
    expect(lastCall.prior + lastCall.consensus).toBe(100);
  });

  it("auto-complements the other weight when a number input is typed", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 70 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "35");

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBe(35);
    expect(lastCall.consensus).toBe(65);
    expect(lastCall.prior + lastCall.consensus).toBe(100);
  });

  it("keeps the pair valid (never shows the red 'Sums' message) after normal input interaction", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 70 };
    const { rerender } = render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "40");

    // Re-render with the newest committed weights, mimicking the parent state.
    const next = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    rerender(<ScoreWeights weights={next} onChange={onChange} />);

    expect(screen.queryByText(/adjust to total 100/i)).not.toBeInTheDocument();
    expect(screen.getByText(/sums 100/i)).toBeInTheDocument();
  });

  it("clamps input values above 100 and complements to 0", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 70 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "150");

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBeLessThanOrEqual(100);
    expect(lastCall.prior + lastCall.consensus).toBe(100);
  });
});
