import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreWeights } from "@/components/ScoreWeights";
import type { Weights } from "@/lib/weights";

describe("ScoreWeights", () => {
  it("renders all three weight values as percentages", () => {
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByDisplayValue("40")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("30")).toHaveLength(2);
  });

  it("shows the 'sums 100%' indicator when valid", () => {
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/sums 100/i)).toBeInTheDocument();
  });

  it("shows an invalid-sum message when weights don't add to 100", () => {
    const weights: Weights = { prior: 30, consensus: 40, adp: 20 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/90/)).toBeInTheDocument();
    expect(screen.getByText(/adjust to total 100/i)).toBeInTheDocument();
  });

  it("calls onChange with only the changed weight when a slider is adjusted", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    const user = userEvent.setup();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBe(31);
    expect(lastCall.consensus).toBe(40);  // unchanged
    expect(lastCall.adp).toBe(30);  // unchanged
  });

  it("calls onChange with only the changed weight when a number input is typed", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "60");

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBe(60);
    expect(lastCall.consensus).toBe(40);
    expect(lastCall.adp).toBe(30);
  });

  it("clamps input values above 100", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "150");

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBeLessThanOrEqual(100);
  });
});
