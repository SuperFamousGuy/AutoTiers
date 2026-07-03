import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RulesPanel } from "@/components/RulesPanel";
import type { Rule, PositionRulesState } from "@/api/types";

// Minimal canonical rules covering the default RB tab and the QB tab.
// Names must match POSITION_RULES_MAP exactly.
const rbCommitteeRule: Rule = {
  name: "RB Committee Penalty",
  conditions: [{ field: "carry_share", operator: "<", value: 0.5 }],
  effect: { type: "multiplier", value: 0.85 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Usage",
  description: "Penalizes RBs in committee backfields. -15%.",
  positions: ["RB"],
};

const newTeamRule: Rule = {
  name: "New Team Penalty",
  conditions: [{ field: "new_team", operator: "==", value: true }],
  effect: { type: "multiplier", value: 0.9 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Situation",
  description: "Penalizes players on new teams. -10%.",
  positions: null,
};

// Used for tests that only need the default RB tab (one rule → one switch).
const rbOnlyCanonical: Rule[] = [rbCommitteeRule];

// Used for tests that need rules across multiple positions.
const minimalCanonical: Rule[] = [rbCommitteeRule, newTeamRule];

describe("RulesPanel", () => {
  it("shows loading state with disabled tabs when canonicalRules is empty", () => {
    render(<RulesPanel canonicalRules={[]} positionRules={{}} onChange={() => {}} />);

    expect(screen.getByText("Loading rules…")).toBeInTheDocument();

    // All 6 position tabs should be rendered but disabled
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    tabs.forEach((tab) => expect(tab).toBeDisabled());
  });

  it("renders position tab strip with RB active by default", () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);

    const rbTab = screen.getByRole("tab", { name: "RB" });
    expect(rbTab).toHaveAttribute("aria-selected", "true");

    const qbTab = screen.getByRole("tab", { name: "QB" });
    expect(qbTab).toHaveAttribute("aria-selected", "false");
  });

  it("clicking a tab switches the active position", async () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);
    const user = userEvent.setup();

    const qbTab = screen.getByRole("tab", { name: "QB" });
    await user.click(qbTab);

    expect(qbTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "RB" })).toHaveAttribute("aria-selected", "false");
  });

  it("ArrowRight keyboard moves focus to the next tab", () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);

    // QB is index 0; fire ArrowRight on it → should activate RB (index 1)
    const qbTab = screen.getByRole("tab", { name: "QB" });
    // First click QB to make it active
    fireEvent.click(qbTab);
    expect(qbTab).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(qbTab, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "RB" })).toHaveAttribute("aria-selected", "true");
  });

  it("ArrowLeft keyboard moves focus to the previous tab", () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);

    // RB is default active (index 1); ArrowLeft → QB (index 0)
    const rbTab = screen.getByRole("tab", { name: "RB" });
    fireEvent.keyDown(rbTab, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "QB" })).toHaveAttribute("aria-selected", "true");
  });

  it("ArrowRight wraps from last tab (DST) to first (QB)", () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);

    const dstTab = screen.getByRole("tab", { name: "DST" });
    fireEvent.click(dstTab);
    fireEvent.keyDown(dstTab, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "QB" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows RB rules on the default RB tab", () => {
    render(<RulesPanel canonicalRules={minimalCanonical} positionRules={{}} onChange={() => {}} />);
    // RB Committee Penalty is in the RB mapping
    expect(screen.getByText("RB Committee Penalty")).toBeInTheDocument();
  });

  it("updateRule appends a new override when none exists (existsIdx < 0)", async () => {
    const onChange = vi.fn();
    // rbOnlyCanonical has one rule on the RB tab → one switch
    render(
      <RulesPanel
        canonicalRules={rbOnlyCanonical}
        positionRules={{}}
        onChange={onChange}
      />
    );
    const user = userEvent.setup();

    // Toggle the switch for RB Committee Penalty (disables it)
    const sw = screen.getByRole("switch");
    await user.click(sw);

    // onChange should have been called with a new override for RB
    expect(onChange).toHaveBeenCalledWith({
      RB: [{ name: "RB Committee Penalty", enabled: false, weight: 1.0 }],
    });
  });

  it("updateRule replaces an existing override when one already exists (existsIdx >= 0)", async () => {
    const onChange = vi.fn();
    const existingOverrides: PositionRulesState = {
      RB: [{ name: "RB Committee Penalty", enabled: false, weight: 1.0 }],
    };

    render(
      <RulesPanel
        canonicalRules={rbOnlyCanonical}
        positionRules={existingOverrides}
        onChange={onChange}
      />
    );
    const user = userEvent.setup();

    // The switch is currently off (enabled=false from override). Click it to re-enable.
    const sw = screen.getByRole("switch");
    await user.click(sw);

    // Should replace, not append — still one entry
    expect(onChange).toHaveBeenCalledWith({
      RB: [{ name: "RB Committee Penalty", enabled: true, weight: 1.0 }],
    });
  });

  it("updateRule preserves overrides for other positions when updating one", async () => {
    const onChange = vi.fn();
    const existingOverrides: PositionRulesState = {
      QB: [{ name: "New Team Penalty", enabled: false, weight: 1.0 }],
    };

    // rbOnlyCanonical → one switch on the RB tab (RB Committee Penalty)
    render(
      <RulesPanel
        canonicalRules={rbOnlyCanonical}
        positionRules={existingOverrides}
        onChange={onChange}
      />
    );
    const user = userEvent.setup();

    // On the default RB tab, toggle RB Committee Penalty
    const sw = screen.getByRole("switch");
    await user.click(sw);

    const called = onChange.mock.calls[0][0] as PositionRulesState;
    // QB overrides must still be present
    expect(called.QB).toEqual([{ name: "New Team Penalty", enabled: false, weight: 1.0 }]);
    // RB override was added
    expect(called.RB).toEqual([{ name: "RB Committee Penalty", enabled: false, weight: 1.0 }]);
  });

  it("renders the error state (not loading) when isError is true", () => {
    render(
      <RulesPanel
        canonicalRules={[]}
        positionRules={{}}
        onChange={() => {}}
        isError
        onRetry={() => {}}
      />
    );

    // Error copy is shown; the loading spinner text is NOT.
    expect(screen.getByText("Couldn't load rules.")).toBeInTheDocument();
    expect(screen.queryByText("Loading rules\u2026")).not.toBeInTheDocument();

    // A retry affordance is present and accessible by name.
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();

    // The whole panel is announced as an alert.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("isError takes precedence over the empty-rules loading check", () => {
    // canonicalRules is [] AND isError — a failed fetch never seeds rules, so
    // this is the real production shape. Must render ERROR, never LOADING.
    render(
      <RulesPanel
        canonicalRules={[]}
        positionRules={{}}
        onChange={() => {}}
        isError
        onRetry={() => {}}
      />
    );
    expect(screen.getByText("Couldn't load rules.")).toBeInTheDocument();
    expect(screen.queryByText("Loading rules\u2026")).not.toBeInTheDocument();
  });

  it("clicking Retry calls onRetry", async () => {
    const onRetry = vi.fn();
    render(
      <RulesPanel
        canonicalRules={[]}
        positionRules={{}}
        onChange={() => {}}
        isError
        onRetry={onRetry}
      />
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not show the error state when isError is false and rules are present", () => {
    render(
      <RulesPanel
        canonicalRules={minimalCanonical}
        positionRules={{}}
        onChange={() => {}}
        isError={false}
      />
    );
    expect(screen.queryByText("Couldn't load rules.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    // Rules render normally.
    expect(screen.getByText("RB Committee Penalty")).toBeInTheDocument();
  });
});
