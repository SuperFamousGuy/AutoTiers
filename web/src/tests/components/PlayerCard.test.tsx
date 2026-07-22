import { describe, it, expect } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
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

  it("shows gold star with accessible name when isFavPlayer is true", () => {
    render(<PlayerCard player={basePlayer} isFavPlayer />);
    const star = screen.getByRole("img", { name: "Favorite player" });
    expect(star).toBeInTheDocument();
    expect(star).toHaveTextContent("⭐");
  });

  it("does not show gold star when isFavPlayer is omitted or false", () => {
    const { rerender } = render(<PlayerCard player={basePlayer} />);
    expect(screen.queryByRole("img", { name: "Favorite player" })).not.toBeInTheDocument();
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
    rerender(<PlayerCard player={basePlayer} isFavPlayer={false} />);
    expect(screen.queryByRole("img", { name: "Favorite player" })).not.toBeInTheDocument();
    expect(screen.queryByText("⭐")).not.toBeInTheDocument();
  });

  it("shows team logo badge when isFavTeam is true", () => {
    render(<PlayerCard player={basePlayer} isFavTeam />);
    // The small badge img has alt = full team name; aria-hidden logo is separate
    const badges = screen.getAllByAltText("Baltimore Ravens");
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("team logo src uses ESPN CDN (not Sleeper) for both badge and card logo", () => {
    render(<PlayerCard player={basePlayer} isFavTeam />);
    const imgs = screen.getAllByAltText("Baltimore Ravens") as HTMLImageElement[];
    for (const img of imgs) {
      expect(img.src).toContain("espncdn.com");
      expect(img.src).not.toContain("sleepercdn.com");
    }
  });

  it("renders the VBD breakdown with replacement and total when expanded", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));
    const vbd = screen.getByText(/Value-Based Drafting/).parentElement!;
    expect(within(vbd).getByText("Replacement (RB)")).toBeInTheDocument();
    expect(within(vbd).getByText(/155\.9/)).toBeInTheDocument();
  });

  it("lazy-loads the player headshot to avoid eager off-domain image requests", () => {
    // Guards issue #628: on the default "ALL" filter TiersPanel renders every
    // PlayerCard with no virtualization, so an eager headshot fires 150-300+
    // sleepercdn.com requests on mount — costly on live-draft venue wifi.
    render(<PlayerCard player={basePlayer} />);
    const headshot = screen.getByAltText(basePlayer.name) as HTMLImageElement;
    expect(headshot.tagName).toBe("IMG");
    expect(headshot.getAttribute("loading")).toBe("lazy");
    expect(headshot.getAttribute("decoding")).toBe("async");
    // Sanity: it is the sleepercdn headshot, not a team logo.
    expect(headshot.src).toContain("sleepercdn.com");
  });

  it("preserves the imgError fallback (position badge) when the headshot fails to load", () => {
    render(<PlayerCard player={basePlayer} />);
    const headshot = screen.getByAltText(basePlayer.name) as HTMLImageElement;
    // Count position-text occurrences up front: the position (e.g. "RB") can
    // already appear elsewhere in the card, so a bare presence check would pass
    // even if the fallback badge never rendered. Assert the badge ADDS one.
    const before = screen.queryAllByText(basePlayer.position).length;
    fireEvent.error(headshot);
    // Headshot img is gone; the position-letter fallback renders in its place.
    expect(screen.queryByAltText(basePlayer.name)).toBeNull();
    expect(screen.queryAllByText(basePlayer.position).length).toBe(before + 1);
  });

  it("renders em-dash for missing team", () => {
    render(<PlayerCard player={{ ...basePlayer, team: null }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("applies team color background tint when isFavTeam is true", () => {
    const { container } = render(
      <PlayerCard player={basePlayer} isFavTeam />
    );
    const card = container.firstChild as HTMLElement;
    expect(card.style.backgroundColor).not.toBe("");
  });

  it("renders no team logo images when team is null even with isFavTeam true", () => {
    render(
      <PlayerCard player={{ ...basePlayer, team: null }} isFavTeam />
    );
    // fullTeamName is "—" when team is null; no logo img should render with that alt
    expect(screen.queryByAltText("—")).toBeNull();
  });

  it("omits score-breakdown rows whose values are null", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      prior_year_actual: null,
      espn_projection: null,
      fantasypros_projection: null,
      avg_projection: null,
    };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.queryByText("Prior year actual")).not.toBeInTheDocument();
    expect(screen.queryByText("ESPN projection")).not.toBeInTheDocument();
    expect(screen.queryByText("FantasyPros consensus")).not.toBeInTheDocument();
    expect(screen.queryByText(/Avg projection/)).not.toBeInTheDocument();
    expect(screen.getByText("Blended raw")).toBeInTheDocument();
  });

  it("filters flag-type rules out of Rule adjustments", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    const ruleSection = screen.getByText("Rule adjustments").parentElement!;
    expect(within(ruleSection).getByText("Red Zone Usage Premium")).toBeInTheDocument();
  });

  it("shows 'No score adjustments' when only flag rules fired", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      rule_applications: [
        { name: "Handcuff", effect_type: "flag", before_score: 100, after_score: 100, delta: 0 },
      ],
    };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText(/No score adjustments/i)).toBeInTheDocument();
    expect(screen.queryByText("Rule adjustments")).not.toBeInTheDocument();
  });

  it("shows 'No score adjustments' when no rules fired", async () => {
    const player: TieredPlayer = { ...basePlayer, rule_applications: [], flags: [] };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText(/No score adjustments/i)).toBeInTheDocument();
  });

  it("color-codes positive and negative deltas", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      rule_applications: [
        { name: "Boost", effect_type: "multiplier", before_score: 234.82, after_score: 251.26, delta: 16.44 },
        { name: "Penalty", effect_type: "multiplier", before_score: 251.26, after_score: 213.57, delta: -37.69 },
      ],
    };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    const positiveDelta = screen.getByText(/\+16\.4/);
    expect(positiveDelta.className).toContain("text-green");

    const negativeDelta = screen.getByText(/-37\.7/);
    expect(negativeDelta.className).toContain("text-red");
  });

  it("hides the Flags section when there are no flags", async () => {
    const player: TieredPlayer = { ...basePlayer, flags: [] };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.queryByText("Flags")).not.toBeInTheDocument();
  });

  it("renders all three ADP variants in the Reference grid", async () => {
    render(<PlayerCard player={basePlayer} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getByText("ADP (standard)")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("ADP (PPR)")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
    expect(screen.getByText("ADP (dynasty)")).toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
  });

  it("renders em-dash for missing ADPs", async () => {
    const player: TieredPlayer = {
      ...basePlayer,
      age: null,
      adp_standard: null,
      adp_ppr: null,
      adp_dynasty: null,
    };
    render(<PlayerCard player={player} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/toggle details/i));

    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
  });
});
