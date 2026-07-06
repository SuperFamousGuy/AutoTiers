import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TiersPanel } from "@/components/TiersPanel";
import generateResponse from "../fixtures/generate-response.json";
import type { GenerateResponse } from "@/api/types";

const response = generateResponse as GenerateResponse;

const tier7Response: GenerateResponse = {
  total: 1,
  data_as_of: null,
  never_succeeded: [],
  players: [
    {
      overall_rank: 1,
      player_id: "9999",
      name: "Test Player",
      position: "WR",
      team: "FA",
      age: null,
      overall_tier: 7,
      positional_tier: "WR7",
      adjusted_score: 50.0,
      projected_score_raw: 50.0,
      prior_year_actual: null,
      espn_projection: null,
      fantasypros_projection: null,
      avg_projection: null,
      adp_standard: null,
      adp_ppr: null,
      adp_dynasty: null,
      league_adp: null,
      vbd_score: 0.0,
      position_replacement: 50.0,
      flags: [],
      rules_applied: [],
      rule_applications: [],
      is_favorite_player: null,
      is_favorite_team: null,
    },
  ],
};

describe("TiersPanel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows placeholder when no result", () => {
    render(<TiersPanel result={null} isPending={false} onDownloadXlsx={() => {}} />);
    expect(screen.getByText(/click generate/i)).toBeInTheDocument();
  });

  it("shows skeleton when pending", () => {
    render(<TiersPanel result={null} isPending={true} onDownloadXlsx={() => {}} />);
    expect(screen.getByText(/generating/i)).toBeInTheDocument();
  });

  it("renders all players grouped by tier", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
    expect(screen.getByText("Josh Allen")).toBeInTheDocument();
  });

  it("renders tier headers", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    expect(screen.getByText(/tier 1/i)).toBeInTheDocument();
    expect(screen.getByText(/tier 2/i)).toBeInTheDocument();
  });

  it("shows descriptive label 'Elite' in the Tier 1 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    // Verify "Elite" is co-located with "Tier 1" in the same header span, not elsewhere in the DOM.
    // eliteEl.parentElement is the outer bold <span> that also contains the tier number text node.
    const eliteEl = screen.getByText("Elite");
    expect(eliteEl.parentElement).toHaveTextContent(/Tier 1/);
  });

  it("shows descriptive label 'Strong Starter' in the Tier 2 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const starterEl = screen.getByText("Strong Starter");
    expect(starterEl.parentElement).toHaveTextContent(/Tier 2/);
  });

  it("shows 'Deep Sleepers' label in the Tier 7 header span (tier 7 is now named)", () => {
    render(<TiersPanel result={tier7Response} isPending={false} onDownloadXlsx={() => {}} />);
    const deepSleepersEl = screen.getByText("Deep Sleepers");
    expect(deepSleepersEl.parentElement).toHaveTextContent(/Tier 7/);
  });

  it("does not show ALL-view descriptive labels when WR position filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    // ALL-view labels disappear when position-filtered
    expect(screen.queryByText("Elite")).not.toBeInTheDocument();
    expect(screen.queryByText("Strong Starter")).not.toBeInTheDocument();
  });

  it("shows 'Flex WR' descriptive label for WR4 when WR filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    const flexWREl = screen.getByText("Flex WR");
    expect(flexWREl.parentElement).toHaveTextContent(/WR4/);
  });

  it("shows 'Elite TE' descriptive label for TE1 when TE filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^te$/i }));
    const eliteTEEl = screen.getByText("Elite TE");
    expect(eliteTEEl.parentElement).toHaveTextContent(/TE1/);
  });

  it("shows 'Elite QB' descriptive label for QB1 when QB filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^qb$/i }));
    const eliteQBEl = screen.getByText("Elite QB");
    expect(eliteQBEl.parentElement).toHaveTextContent(/QB1/);
  });

  it("filters by position when a position chip is clicked", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Justin Jefferson")).toBeInTheDocument();
    expect(screen.queryByText("Bijan Robinson")).not.toBeInTheDocument();
    expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  });

  it("groups by positional tier when filtered to a position", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    // Now the tier headers should be position-relative (WR1, WR2) not overall (Tier 1, Tier 2).
    expect(screen.getByText(/WR1/)).toBeInTheDocument();
    expect(screen.getByText(/WR2/)).toBeInTheDocument();
  });

  it("calls onDownloadXlsx when the Excel download button is clicked", async () => {
    const onDownload = vi.fn();
    render(<TiersPanel result={response} isPending={false} onDownloadXlsx={onDownload} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^download excel$/i }));
    expect(onDownload).toHaveBeenCalled();
  });

  describe("debug CSV button", () => {
    it("is hidden when debugMode is falsy", () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      expect(screen.queryByRole("button", { name: /download debug csv/i })).not.toBeInTheDocument();
    });

    it("is shown when debugMode is true", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          debugMode={true}
          onDownloadDebugCsv={() => {}}
        />,
      );
      expect(screen.getByRole("button", { name: /download debug csv/i })).toBeInTheDocument();
    });

    it("calls onDownloadDebugCsv when clicked", async () => {
      const onDebug = vi.fn();
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          debugMode={true}
          onDownloadDebugCsv={onDebug}
        />,
      );
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: /download debug csv/i }));
      expect(onDebug).toHaveBeenCalled();
    });
  });

  describe("tierLabelOverrides", () => {
    it("shows override label 'Studs' in the Tier 1 header when tierLabelOverrides={{ 1: 'Studs' }}", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          tierLabelOverrides={{ 1: "Studs" }}
        />,
      );
      const studsEl = screen.getByText("Studs");
      expect(studsEl.parentElement).toHaveTextContent(/Tier 1/);
    });

    it("does not show 'Elite' when tier 1 is overridden with 'Studs'", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          tierLabelOverrides={{ 1: "Studs" }}
        />,
      );
      expect(screen.queryByText("Elite")).not.toBeInTheDocument();
    });

    it("shows 'Elite' when tierLabelOverrides is undefined", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          tierLabelOverrides={undefined}
        />,
      );
      const eliteEl = screen.getByText("Elite");
      expect(eliteEl.parentElement).toHaveTextContent(/Tier 1/);
    });

    it("shows static defaults for tiers not covered by override map", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          tierLabelOverrides={{ 1: "Studs" }}
        />,
      );
      // Tier 2 is not overridden, should show "Strong Starter"
      const starterEl = screen.getByText("Strong Starter");
      expect(starterEl.parentElement).toHaveTextContent(/Tier 2/);
    });
  });

  describe("draft mode", () => {
    it("does not show the draft toggle button on player rows until Draft Mode is on", () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      expect(screen.queryByRole("button", { name: /mark ja'marr chase as drafted/i })).not.toBeInTheDocument();
    });

    it("toggling Draft Mode on reveals per-player draft affordances", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      expect(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i })).toBeInTheDocument();
    });

    it("Draft Mode toggle exposes aria-checked state", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      const toggle = screen.getByRole("switch", { name: /draft mode/i });
      expect(toggle).toHaveAttribute("aria-checked", "false");
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });

    it("clicking a player's draft button marks it drafted: strike-through + header count", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));

      // Header shows "1 drafted"
      expect(screen.getByText(/1 drafted/i)).toBeInTheDocument();

      // The name now has strike-through styling in the player row (a <span>;
      // the Drafted section below renders the same name as a plain <button>).
      const nameEls = screen.getAllByText("Ja'Marr Chase");
      const rowNameEl = nameEls.find((el) => el.tagName === "SPAN")!;
      expect(rowNameEl.className).toContain("line-through");

      // The toggle button's accessible name flips to "available"
      expect(screen.getByRole("button", { name: /mark ja'marr chase as available/i })).toBeInTheDocument();
    });

    it("clicking the draft toggle again un-drafts the player", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      expect(screen.getByText(/1 drafted/i)).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as available/i }));
      expect(screen.queryByText(/1 drafted/i)).not.toBeInTheDocument();
      const nameEl = screen.getByText("Ja'Marr Chase");
      expect(nameEl.tagName).toBe("SPAN");
      expect(nameEl.className).not.toContain("line-through");
    });

    it("Reset Draft clears all drafted players", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      await user.click(screen.getByRole("button", { name: /mark bijan robinson as drafted/i }));
      expect(screen.getByText(/2 drafted/i)).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /^reset draft$/i }));
      // Header suffix now reads "0 drafted" (still in Draft Mode), not "2 drafted".
      expect(screen.getByText(/0 drafted/i)).toBeInTheDocument();
      expect(screen.queryByText(/2 drafted/i)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /mark bijan robinson as drafted/i })).toBeInTheDocument();
    });

    it("the available-count badge for Tier 1 drops from 2 to 1 after drafting one of its players", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));

      // Tier 1 contains Ja'Marr Chase and Bijan Robinson (2 players) in the fixture.
      const tier1Header = screen.getByText(/^Tier 1$/).closest("div")!;
      expect(within(tier1Header).getByText("2 players")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      expect(within(tier1Header).getByText("1 player")).toBeInTheDocument();
    });

    it("shows the collapsible 'Drafted' section only when draft mode is on and at least one player is drafted", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      expect(screen.queryByText(/^Drafted \(/)).not.toBeInTheDocument();

      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      expect(screen.queryByText(/^Drafted \(/)).not.toBeInTheDocument(); // 0 drafted yet

      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      expect(screen.getByText("Drafted (1)")).toBeInTheDocument();
    });

    it("clicking a name in the Drafted section un-drafts that player", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));

      const draftedSection = screen.getByText("Drafted (1)").closest("details")!;
      await user.click(within(draftedSection).getByText("Ja'Marr Chase"));

      expect(screen.queryByText(/^Drafted \(/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i })).toBeInTheDocument();
    });

    it("turning Draft Mode back off hides the draft affordances but keeps the count for next time (persisted via the hook)", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      const toggle = screen.getByRole("switch", { name: /draft mode/i });
      await user.click(toggle);
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      await user.click(toggle); // turn draft mode off

      expect(screen.queryByRole("button", { name: /mark ja'marr chase as (drafted|available)/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/drafted/i, { selector: "p" })).not.toBeInTheDocument();

      // Turning Draft Mode back on must reveal the previously-drafted player as
      // still drafted — i.e. the drafted set was kept, not cleared, while off.
      await user.click(toggle); // turn draft mode back on
      expect(screen.getByText(/1 drafted/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /mark ja'marr chase as available/i }),
      ).toBeInTheDocument();
    });
  });
});
