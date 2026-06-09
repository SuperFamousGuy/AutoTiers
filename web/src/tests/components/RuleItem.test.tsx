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
  positions: null,
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

  describe("positions toggle", () => {
    it("shows the positions group when expanded", async () => {
      render(<RuleItem rule={baseRule} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      expect(screen.getByRole("group", { name: /position scope/i })).toBeInTheDocument();
    });

    it("'All' button is active by default when positions is null", async () => {
      render(<RuleItem rule={{ ...baseRule, positions: null }} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      const allBtn = screen.getByRole("button", { name: /apply to all positions/i });
      expect(allBtn).toHaveAttribute("aria-pressed", "true");
    });

    it("'All' button is active when positions is empty array", async () => {
      render(<RuleItem rule={{ ...baseRule, positions: [] }} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      const allBtn = screen.getByRole("button", { name: /apply to all positions/i });
      expect(allBtn).toHaveAttribute("aria-pressed", "true");
    });

    it("position button shows as active when that position is in the array", async () => {
      render(<RuleItem rule={{ ...baseRule, positions: ["WR", "TE"] }} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      expect(screen.getByRole("button", { name: /toggle wr/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /toggle te/i })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: /toggle rb/i })).toHaveAttribute("aria-pressed", "false");
    });

    it("clicking a position button adds it to positions and calls onChange", async () => {
      const onChange = vi.fn();
      render(<RuleItem rule={{ ...baseRule, positions: null }} onChange={onChange} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      await user.click(screen.getByRole("button", { name: /toggle rb/i }));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ positions: ["RB"] }),
      );
    });

    it("clicking an active position button removes it from positions", async () => {
      const onChange = vi.fn();
      render(<RuleItem rule={{ ...baseRule, positions: ["WR", "TE"] }} onChange={onChange} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      await user.click(screen.getByRole("button", { name: /toggle wr/i }));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ positions: ["TE"] }),
      );
    });

    it("clicking 'All' sets positions to null", async () => {
      const onChange = vi.fn();
      render(<RuleItem rule={{ ...baseRule, positions: ["WR"] }} onChange={onChange} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      await user.click(screen.getByRole("button", { name: /apply to all positions/i }));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ positions: null }),
      );
    });

    it("selecting all individual positions reverts positions to null", async () => {
      const onChange = vi.fn();
      // Start with 5 positions (missing DST)
      render(
        <RuleItem
          rule={{ ...baseRule, positions: ["QB", "RB", "WR", "TE", "K"] }}
          onChange={onChange}
        />,
      );
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for test rule/i));

      // Adding DST completes all 6 — should revert to null
      await user.click(screen.getByRole("button", { name: /toggle dst/i }));

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ positions: null }),
      );
    });

    it("locked rule renders positions as plain text badges with (locked) label", async () => {
      const lockedRule: Rule = {
        ...baseRule,
        name: "370 Touches",
        positions: ["RB"],
        is_builtin: true,
      };
      render(<RuleItem rule={lockedRule} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for 370 touches/i));

      expect(screen.getByText("RB")).toBeInTheDocument();
      expect(screen.getByText("(locked)")).toBeInTheDocument();
      // No interactive toggle group
      expect(screen.queryByRole("group", { name: /position scope/i })).not.toBeInTheDocument();
    });

    it("locked rule does not render position toggle buttons", async () => {
      const lockedRule: Rule = {
        ...baseRule,
        name: "Handcuff RB",
        positions: ["RB"],
        is_builtin: true,
      };
      render(<RuleItem rule={lockedRule} onChange={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByLabelText(/toggle details for handcuff rb/i));

      expect(screen.queryByRole("button", { name: /toggle rb/i })).not.toBeInTheDocument();
    });
  });
});
