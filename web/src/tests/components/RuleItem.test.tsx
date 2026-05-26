import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleItem } from "@/components/RuleItem";
import type { Rule } from "@/api/types";

const baseRule: Rule = {
  name: "Test Rule",
  conditions: [{ field: "age", operator: ">", value: 30 }],
  effect: { type: "multiplier", value: 0.9 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Age/Longevity",
  description: "Penalizes old players. -10%.",
};

describe("RuleItem", () => {
  it("renders the rule name", () => {
    render(<RuleItem rule={baseRule} onChange={() => {}} />);
    expect(screen.getByText("Test Rule")).toBeInTheDocument();
  });

  it("calls onChange when the switch is toggled", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    expect(onChange).toHaveBeenCalledWith({ ...baseRule, enabled: false });
  });

  it("does not show description or adjustment row until expanded", () => {
    render(<RuleItem rule={baseRule} onChange={() => {}} />);
    expect(screen.queryByText(baseRule.description!)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/adjustment magnitude/i)).not.toBeInTheDocument();
  });

  it("shows description and adjustment row when expanded", async () => {
    render(<RuleItem rule={baseRule} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    expect(screen.getByText(baseRule.description!)).toBeInTheDocument();
    expect(screen.getByLabelText(/test rule adjustment magnitude/i)).toBeInTheDocument();
  });

  it("clicking the High suggestion sets weight to 2.0", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    // For a -10% rule (effect.value=0.9), High shows -20%.
    await user.click(screen.getByRole("button", { name: /high: −20%/i }));
    expect(onChange).toHaveBeenCalledWith({ ...baseRule, weight: 2.0 });
  });

  it("clicking the Low suggestion sets weight to 0.5", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    await user.click(screen.getByRole("button", { name: /low: −5%/i }));
    expect(onChange).toHaveBeenCalledWith({ ...baseRule, weight: 0.5 });
  });

  it("typing a custom magnitude updates weight on blur", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    const input = screen.getByLabelText(/test rule adjustment magnitude/i);
    await user.clear(input);
    await user.type(input, "15");
    await user.tab();  // blur

    // 15% on a rule with intrinsic 10% impact → weight = 1.5
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ weight: 1.5 }));
  });

  it("input reflects external weight changes (suggestion clicks persist visually)", async () => {
    const { rerender } = render(<RuleItem rule={baseRule} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    // Simulate parent updating the rule after a High click — weight becomes 2.0
    rerender(<RuleItem rule={{ ...baseRule, weight: 2.0 }} onChange={() => {}} />);
    const input = screen.getByLabelText(/test rule adjustment magnitude/i) as HTMLInputElement;
    expect(input.value).toBe("20");
  });

  it("works for flat_penalty rules (input shown in points)", async () => {
    const flatRule: Rule = {
      ...baseRule,
      effect: { type: "flat_penalty", value: 5.0 },
      description: "Flat penalty of 5 points.",
    };
    const onChange = vi.fn();
    render(<RuleItem rule={flatRule} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    expect(screen.getByRole("button", { name: /low: −2\.5 pts/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /high: −10 pts/i })).toBeInTheDocument();

    const input = screen.getByLabelText(/test rule adjustment magnitude/i) as HTMLInputElement;
    expect(input.value).toBe("5");

    await user.clear(input);
    await user.type(input, "8");
    await user.tab();
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ weight: 1.6 }));
  });

  it("disables suggestion buttons and input when the rule is disabled", async () => {
    render(<RuleItem rule={{ ...baseRule, enabled: false }} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    expect(screen.getByRole("button", { name: /low:/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /high:/i })).toBeDisabled();
    expect(screen.getByLabelText(/test rule adjustment magnitude/i)).toBeDisabled();
  });
});
