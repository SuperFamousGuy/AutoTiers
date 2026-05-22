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
};

describe("RuleItem", () => {
  it("renders the rule name", () => {
    render(<RuleItem rule={baseRule} onChange={() => {}} />);
    expect(screen.getByText("Test Rule")).toBeInTheDocument();
  });

  it("calls onChange when toggle is clicked", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    expect(onChange).toHaveBeenCalledWith({ ...baseRule, enabled: false });
  });

  it("calls onChange when weight chip is changed", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /high/i }));

    expect(onChange).toHaveBeenCalledWith({ ...baseRule, weight: 2.0 });
  });
});
