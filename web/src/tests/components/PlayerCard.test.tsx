import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlayerCard } from "@/components/PlayerCard";
import type { TieredPlayer } from "@/api/types";

const basePlayer: TieredPlayer = {
  overall_rank: 7,
  player_id: "4035",
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
  rules_applied: ["Red Zone Usage Premium"],
  rule_applications: [
    {
      name: "Red Zone Usage Premium",
      effect_type: "multiplier",
      before_score: 234.82,
      after_score: 251.26,
      delta: 16.44,
    },
  ],
  is_favorite_player: null,
  is_favorite_team: null,
};

describe("PlayerCard", () => {
  it("renders rank, name, team abbreviation in subtitle, and VBD score collapsed", () => {
    render(<PlayerCard player={basePlayer} />);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Derrick Henry")).toBeInTheDocument();
    expect(screen.getByText("95.4")).toBeInTheDocument();
    // subtitle shows position and full team name
    expect(screen.getByText(/RB/)).toBeInTheDocument();
    expect(screen.getByText(/Baltimore Ravens/)).toBeInTheDocument();
  });

  it("does not show expanded sections when collapsed", () => {
    render(<PlayerCard player={basePlayer} />);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
    expect(screen.queryByText(/Value-Based Drafting/)).not.toBeInTheDocument();
  });

  it("expands on click and shows all detail sections", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details for derrick henry/i));
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    expect(screen.getByText("Rule adjustments")).toBeInTheDocument();
    expect(screen.getByText(/Value-Based Drafting/)).toBeInTheDocument();
    expect(screen.getByText("Flags")).toBeInTheDocument();
    expect(screen.getByText("Tier placement")).toBeInTheDocument();
    expect(screen.getByText("Reference")).toBeInTheDocument();
  });

  it("collapses again when toggled twice", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    const toggle = screen.getByLabelText(/toggle details/i);
    await user.click(toggle);
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    await user.click(toggle);
    expect(screen.queryByText("Score breakdown")).not.toBeInTheDocument();
  });

  it("shows gold star when is_favorite_player is true", () => {
    render(<PlayerCard player={{ ...basePlayer, is_favorite_player: true }} />);
    expect(screen.getByText("⭐")).toBeInTheDocument();
  });

  it("does not show gold star when is_favorite_player is null or false", () => {
    const { rerender } = render(<PlayerCard player={basePlayer} />);
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
    rerender(<PlayerCard player={{ ...basePlayer, is_favorite_player: false }} />);
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
  });

  it("shows team logo badge when is_favorite_team is true", () => {
    render(<PlayerCard player={{ ...basePlayer, is_favorite_team: true }} />);
    // The small badge img has alt = full team name; aria-hidden logo is separate
    const badges = screen.getAllByAltText("Baltimore Ravens");
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("renders the VBD breakdown with replacement and total when expanded", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));
    const vbd = screen.getByText(/Value-Based Drafting/).parentElement!;
    expect(within(vbd).getByText("Replacement (RB)")).toBeInTheDocument();
    expect(within(vbd).getByText(/155\.9/)).toBeInTheDocument();
  });

  it("renders em-dash for missing team", () => {
    render(<PlayerCard player={{ ...basePlayer, team: null }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("applies team color background tint when is_favorite_team is true", () => {
    const { container } = render(
      <PlayerCard player={{ ...basePlayer, is_favorite_team: true }} />
    );
    const card = container.firstChild as HTMLElement;
    expect(card.style.backgroundColor).not.toBe("");
  });

  it("renders no team logo images when team is null even with is_favorite_team true", () => {
    render(
      <PlayerCard player={{ ...basePlayer, team: null, is_favorite_team: true }} />
    );
    // fullTeamName is "—" when team is null; no logo img should render with that alt
    expect(screen.queryByAltText("—")).toBeNull();
  });
});
