import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleCategory } from "@/components/RuleCategory";
import type { Rule, PositionRuleOverride } from "@/api/types";

const baseRule: Rule = {
  name: "Target Share Premium",
  conditions: [{ field: "target_share", operator: ">=", value: 0.25 }],
  effect: { type: "multiplier", value: 1.07 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Usage",
  description: "Boosts WR/TE/RB with elite target share.",
  positions: ["RB", "WR", "TE"],
};

const secondRule: Rule = {
  name: "Declining Snap%",
  conditions: [{ field: "snap_pct", operator: "<", value: 0.55 }],
  effect: { type: "multiplier", value: 0.9 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Usage",
  description: "Penalizes low snap share.",
  positions: ["RB", "WR", "TE"],
};

describe("RuleCategory", () => {
  it("renders the category name", () => {
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule]}
        overrides={{}}
        onChangeRule={() => {}}
      />
    );
    expect(screen.getByText("Usage")).toBeInTheDocument();
  });

  it("renders all rule names in the category", () => {
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule, secondRule]}
        overrides={{}}
        onChangeRule={() => {}}
      />
    );
    expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    expect(screen.getByText("Declining Snap%")).toBeInTheDocument();
  });

  it("passes default override (enabled=true, weight from rule) when no override exists", () => {
    const onChange = vi.fn();
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule]}
        overrides={{}}
        onChangeRule={onChange}
      />
    );
    // Two switches rendered (one per rule, here one rule)
    const sw = screen.getByRole("switch");
    // Switch should be checked (enabled=true by default)
    expect(sw).toHaveAttribute("data-state", "checked");
  });

  it("passes the correct override when one exists", () => {
    const overrides: Record<string, PositionRuleOverride> = {
      "Target Share Premium": { name: "Target Share Premium", enabled: false, weight: 0.5 },
    };
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule]}
        overrides={overrides}
        onChangeRule={() => {}}
      />
    );
    const sw = screen.getByRole("switch");
    // Override has enabled=false — switch should be unchecked
    expect(sw).toHaveAttribute("data-state", "unchecked");
  });

  it("calls onChangeRule with PositionRuleOverride when a rule changes", async () => {
    const onChangeRule = vi.fn();
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule]}
        overrides={{}}
        onChangeRule={onChangeRule}
      />
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    // onChange should be called with the PositionRuleOverride shape (name, enabled, weight)
    expect(onChangeRule).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Target Share Premium", enabled: false }),
    );
  });

  it("passes separate overrides to different rules", () => {
    const overrides: Record<string, PositionRuleOverride> = {
      "Target Share Premium": { name: "Target Share Premium", enabled: false, weight: 1.0 },
      // Declining Snap% has no override — should use rule default
    };
    render(
      <RuleCategory
        name="Usage"
        rules={[baseRule, secondRule]}
        overrides={overrides}
        onChangeRule={() => {}}
      />
    );
    const switches = screen.getAllByRole("switch");
    // First rule (Target Share Premium) is disabled
    expect(switches[0]).toHaveAttribute("data-state", "unchecked");
    // Second rule (Declining Snap%) has no override → defaults to enabled
    expect(switches[1]).toHaveAttribute("data-state", "checked");
  });
});
