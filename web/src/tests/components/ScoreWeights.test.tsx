import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreWeights } from "@/components/ScoreWeights";
import type { Weights } from "@/lib/weights";

describe("ScoreWeights", () => {
  it("renders all three weight values as percentages", () => {
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    // The values now appear in number inputs. Verify by display value.
    expect(screen.getByDisplayValue("40")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("30")).toHaveLength(2);
  });

  it("shows the sum and a 'sums 100%' indicator", () => {
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/sums.*100/i)).toBeInTheDocument();
  });

  it("calls onChange with redistributed weights when a slider is adjusted", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    const user = userEvent.setup();
    await user.keyboard("{ArrowRight>10}");

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior + lastCall.consensus + lastCall.adp).toBe(100);
  });

  it("calls onChange when a number input is typed", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "60");

    expect(onChange).toHaveBeenCalled();
    // The last call should have prior=60 with the others redistributed.
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBe(60);
    expect(lastCall.prior + lastCall.consensus + lastCall.adp).toBe(100);
  });

  it("clamps values above 100", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 30, consensus: 40, adp: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    const user = userEvent.setup();
    const priorInput = screen.getByLabelText(/prior year actuals percentage/i);
    await user.clear(priorInput);
    await user.type(priorInput, "150");

    // Last call's prior should be clamped to 100
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior).toBeLessThanOrEqual(100);
  });
});
