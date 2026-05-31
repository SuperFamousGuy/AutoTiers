import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlayerRow } from "@/components/PlayerRow";
import type { TieredPlayer } from "@/api/types";

const basePlayer: TieredPlayer = {
  overall_rank: 7,
  player_id: "rb_henry",
  name: "Derrick Henry",
  position: "RB",
  team: "BAL",
  age: 32,
  overall_tier: 1,
  positional_tier: "RB1",
  adjusted_score: 251.26,
  projected_score_raw: 234.82,
  prior_year_actual: 280.5,
  avg_projection: 220.4,
  espn_projection: 215.0,
  fantasypros_projection: 225.8,
  adp_standard: 18,
  adp_ppr: 16,
  adp_dynasty: 22,
  league_adp: null,
  vbd_score: 95.4,
  position_replacement: 155.9,
  flags: ["Contract Year"],
  rules_applied: ["Red Zone Usage Premium", "Over the Hill", "Contract Year Flag"],
  rule_applications: [
    {
      name: "Red Zone Usage Premium",
      effect_type: "multiplier",
      before_score: 234.82,
      after_score: 251.26,
      delta: 16.44,
    },
    {
      name: "Over the Hill",
      effect_type: "multiplier",
      before_score: 251.26,
      after_score: 213.57,
      delta: -37.69,
    },
    {
      name: "Contract Year Flag",
      effect_type: "flag",
      before_score: 234.82,
      after_score: 234.82,
      delta: 0,
    },
  ],
};

describe("PlayerRow", () => {
  it("renders the collapsed row with rank, name, team, and VBD", () => {
    render(<PlayerRow player={basePlayer} />);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Derrick Henry")).toBeInTheDocument();
    expect(screen.getByText("BAL")).toBeInTheDocument();
    expect(screen.getByText("95.4")).toBeInTheDocument();
  });

  it("does not render expanded sections until clicked", () => {
    render(<PlayerRow player={basePlayer} />);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText("Rule adjustments")).not.toBeInTheDocument();
    expect(screen.queryByText(/Value-Based Drafting/)).not.toBeInTheDocument();
    expect(screen.queryByText("Flags")).not.toBeInTheDocument();
  });

  it("expands on click and shows every section", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for derrick henry/i));

    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    expect(screen.getByText("Rule adjustments")).toBeInTheDocument();
    expect(screen.getByText(/Value-Based Drafting/)).toBeInTheDocument();
    expect(screen.getByText("Flags")).toBeInTheDocument();
    expect(screen.getByText("Tier placement")).toBeInTheDocument();
    expect(screen.getByText("Reference")).toBeInTheDocument();
  });

  it("renders all available score-breakdown source values", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText("Prior year actual")).toBeInTheDocument();
    expect(screen.getByText("280.5")).toBeInTheDocument();
    expect(screen.getByText("ESPN projection")).toBeInTheDocument();
    expect(screen.getByText("215.0")).toBeInTheDocument();
    expect(screen.getByText("FantasyPros consensus")).toBeInTheDocument();
    expect(screen.getByText("225.8")).toBeInTheDocument();
    expect(screen.getByText(/Avg projection/)).toBeInTheDocument();
    expect(screen.getByText("Blended raw")).toBeInTheDocument();
    expect(screen.getByText("234.8")).toBeInTheDocument();
  });

  it("omits score-breakdown rows whose values are null", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      prior_year_actual: null,
      espn_projection: null,
      fantasypros_projection: null,
      avg_projection: null,
    };
    render(<PlayerRow player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.queryByText("Prior year actual")).not.toBeInTheDocument();
    expect(screen.queryByText("ESPN projection")).not.toBeInTheDocument();
    expect(screen.queryByText("FantasyPros consensus")).not.toBeInTheDocument();
    expect(screen.queryByText(/Avg projection/)).not.toBeInTheDocument();
    // Blended raw is always shown
    expect(screen.getByText("Blended raw")).toBeInTheDocument();
  });

  it("filters flag-type rules out of Rule adjustments", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    const ruleAdjustments = screen.getByText("Rule adjustments").parentElement!;
    // Multipliers appear in Rule adjustments
    expect(within(ruleAdjustments).getByText("Red Zone Usage Premium")).toBeInTheDocument();
    expect(within(ruleAdjustments).getByText("Over the Hill")).toBeInTheDocument();
    // Flag rule does NOT appear in Rule adjustments
    expect(within(ruleAdjustments).queryByText("Contract Year Flag")).not.toBeInTheDocument();
  });

  it("color-codes positive and negative deltas", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    // The +16.44 delta should be in a green span
    const positiveDelta = screen.getByText(/\+16\.4/);
    expect(positiveDelta.className).toContain("text-green");

    // The -37.69 delta should be in a red span
    const negativeDelta = screen.getByText(/-37\.7/);
    expect(negativeDelta.className).toContain("text-red");
  });

  it("shows the 'No score adjustments' empty state when only flag rules fired", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      rule_applications: [
        {
          name: "Handcuff",
          effect_type: "flag",
          before_score: 100,
          after_score: 100,
          delta: 0,
        },
      ],
    };
    render(<PlayerRow player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText(/No score adjustments/i)).toBeInTheDocument();
    expect(screen.queryByText("Rule adjustments")).not.toBeInTheDocument();
  });

  it("shows the 'No score adjustments' empty state when no rules fired at all", async () => {
    const player: TieredPlayer = { ...basePlayer, rule_applications: [], flags: [] };
    render(<PlayerRow player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText(/No score adjustments/i)).toBeInTheDocument();
  });

  it("hides the Flags section when there are no flags", async () => {
    const player: TieredPlayer = { ...basePlayer, flags: [] };
    render(<PlayerRow player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.queryByText("Flags")).not.toBeInTheDocument();
  });

  it("renders VBD breakdown with adjusted score, replacement, and VBD total", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    const vbd = screen.getByText(/Value-Based Drafting/).parentElement!;
    expect(within(vbd).getByText("Replacement (RB)")).toBeInTheDocument();
    expect(within(vbd).getByText(/155\.9/)).toBeInTheDocument();
    expect(within(vbd).getByText("VBD score")).toBeInTheDocument();
    expect(within(vbd).getByText("95.4")).toBeInTheDocument();
  });

  it("renders all three ADP variants in the Reference grid", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText("ADP (standard)")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("ADP (PPR)")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.getByText("ADP (dynasty)")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
  });

  it("renders em-dash for missing team and missing ADPs", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      team: null,
      age: null,
      adp_standard: null,
      adp_ppr: null,
      adp_dynasty: null,
    };
    render(<PlayerRow player={player} />);
    expect(screen.getByText("—")).toBeInTheDocument();  // team in collapsed row

    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));
    // age + 3 ADPs + team all show em-dash; collapsed row shows team
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
  });

  it("collapses again when toggled twice", async () => {
    render(<PlayerRow player={basePlayer} />);
    const user = userEvent.setup();
    const toggle = screen.getByLabelText(/toggle details/i);

    await user.click(toggle);
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
  });
});
