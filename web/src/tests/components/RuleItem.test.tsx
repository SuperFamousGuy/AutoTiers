import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleItem } from "@/components/RuleItem";
import type { Rule, PositionRuleOverride } from "@/api/types";

const baseRule: Rule = {
  name: "Test Rule",
  conditions: [{ field: "age", operator: ">", value: 30 }],
  effect: { type: "multiplier", value: 0.9 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Age/Longevity",
  description: "Penalizes old players. -10%.",
  positions: null,
};

const defaultOverride: PositionRuleOverride = {
  name: "Test Rule",
  enabled: true,
  weight: 1.0,
};

describe("RuleItem", () => {
  it("renders the rule name", () => {
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={() => {}} />);
    expect(screen.getByText("Test Rule")).toBeInTheDocument();
  });

  it("switch reflects override.enabled state", () => {
    render(<RuleItem rule={baseRule} override={{ ...defaultOverride, enabled: false }} onChange={() => {}} />);
    const sw = screen.getByRole("switch");
    expect(sw).toHaveAttribute("data-state", "unchecked");
  });

  it("calls onChange with enabled toggled when the switch is clicked", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    expect(onChange).toHaveBeenCalledWith({ ...defaultOverride, enabled: false });
  });

  it("calls onChange with enabled=true when disabled switch is toggled on", async () => {
    const onChange = vi.fn();
    const disabledOverride: PositionRuleOverride = { ...defaultOverride, enabled: false };
    render(<RuleItem rule={baseRule} override={disabledOverride} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    expect(onChange).toHaveBeenCalledWith({ ...disabledOverride, enabled: true });
  });

  it("does not show description or adjustment row until expanded", () => {
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={() => {}} />);
    expect(screen.queryByText(baseRule.description!)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/adjustment magnitude/i)).not.toBeInTheDocument();
  });

  it("shows description and adjustment row when expanded", async () => {
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    expect(screen.getByText(baseRule.description!)).toBeInTheDocument();
    expect(screen.getByLabelText(/test rule adjustment magnitude/i)).toBeInTheDocument();
  });

  it("does NOT render position toggle section", async () => {
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    // No position scope group, no All button, no individual position buttons
    expect(screen.queryByRole("group", { name: /position scope/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply to all positions/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /toggle rb/i })).not.toBeInTheDocument();
  });

  it("impact input reflects override.weight not rule.weight", async () => {
    // rule.weight is 1.0 (default), override.weight is 2.0 (user-customized)
    const weightedOverride: PositionRuleOverride = { ...defaultOverride, weight: 2.0 };
    render(<RuleItem rule={baseRule} override={weightedOverride} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    // For a -10% rule (effect.value=0.9) at weight 2.0 → 20%
    const input = screen.getByLabelText(/test rule adjustment magnitude/i) as HTMLInputElement;
    expect(input.value).toBe("20");
  });

  it("clicking the High suggestion sets weight to 2.0 via override", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    // For a -10% rule (effect.value=0.9), High shows -20%.
    await user.click(screen.getByRole("button", { name: /high: −20%/i }));
    expect(onChange).toHaveBeenCalledWith({ ...defaultOverride, weight: 2.0 });
  });

  it("clicking the Low suggestion sets weight to 0.5 via override", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));
    await user.click(screen.getByRole("button", { name: /low: −5%/i }));
    expect(onChange).toHaveBeenCalledWith({ ...defaultOverride, weight: 0.5 });
  });

  it("typing a custom magnitude updates weight on blur", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} override={defaultOverride} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    const input = screen.getByLabelText(/test rule adjustment magnitude/i);
    await user.clear(input);
    await user.type(input, "15");
    await user.tab();  // blur

    // 15% on a rule with intrinsic 10% impact → weight = 1.5
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ weight: 1.5 }));
  });

  it("input re-syncs when override.weight changes externally", async () => {
    const { rerender } = render(<RuleItem rule={baseRule} override={defaultOverride} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    // Simulate parent updating the override weight to 2.0
    rerender(<RuleItem rule={baseRule} override={{ ...defaultOverride, weight: 2.0 }} onChange={() => {}} />);
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
    render(<RuleItem rule={flatRule} override={defaultOverride} onChange={onChange} />);
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

  it("disables suggestion buttons and input when override.enabled is false", async () => {
    const disabledOverride: PositionRuleOverride = { ...defaultOverride, enabled: false };
    render(<RuleItem rule={baseRule} override={disabledOverride} onChange={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for test rule/i));

    expect(screen.getByRole("button", { name: /low:/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /high:/i })).toBeDisabled();
    expect(screen.getByLabelText(/test rule adjustment magnitude/i)).toBeDisabled();
  });

  it("onChange receives the full override object with all fields", async () => {
    const onChange = vi.fn();
    const customOverride: PositionRuleOverride = { name: "Test Rule", enabled: true, weight: 1.5 };
    render(<RuleItem rule={baseRule} override={customOverride} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    // Should spread the whole override, only toggling enabled
    expect(onChange).toHaveBeenCalledWith({ name: "Test Rule", enabled: false, weight: 1.5 });
  });
});
