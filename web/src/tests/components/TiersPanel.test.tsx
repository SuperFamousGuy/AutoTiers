import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TiersPanel } from "@/components/TiersPanel";
import generateResponse from "../fixtures/generate-response.json";
import type { GenerateResponse } from "@/api/types";

const response = generateResponse as GenerateResponse;

const tier7Response: GenerateResponse = {
  total: 1,
  data_as_of: null,
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
  it("shows placeholder when no result", () => {
    render(<TiersPanel result={null} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/click generate/i)).toBeInTheDocument();
  });

  it("shows skeleton when pending", () => {
    render(<TiersPanel result={null} isPending={true} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/generating/i)).toBeInTheDocument();
  });

  it("renders all players grouped by tier", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
    expect(screen.getByText("Josh Allen")).toBeInTheDocument();
  });

  it("renders tier headers", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/tier 1/i)).toBeInTheDocument();
    expect(screen.getByText(/tier 2/i)).toBeInTheDocument();
  });

  it("shows descriptive label 'Elite' in the Tier 1 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    // Verify "Elite" is co-located with "Tier 1" in the same header span, not elsewhere in the DOM.
    // eliteEl.parentElement is the outer bold <span> that also contains the tier number text node.
    const eliteEl = screen.getByText("Elite");
    expect(eliteEl.parentElement).toHaveTextContent(/Tier 1/);
  });

  it("shows descriptive label 'Strong Starter' in the Tier 2 header span", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const starterEl = screen.getByText("Strong Starter");
    expect(starterEl.parentElement).toHaveTextContent(/Tier 2/);
  });

  it("shows 'Deep Sleepers' label in the Tier 7 header span (tier 7 is now named)", () => {
    render(<TiersPanel result={tier7Response} isPending={false} onDownloadCsv={() => {}} />);
    const deepSleepersEl = screen.getByText("Deep Sleepers");
    expect(deepSleepersEl.parentElement).toHaveTextContent(/Tier 7/);
  });

  it("does not show ALL-view descriptive labels when WR position filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    // ALL-view labels disappear when position-filtered
    expect(screen.queryByText("Elite")).not.toBeInTheDocument();
    expect(screen.queryByText("Strong Starter")).not.toBeInTheDocument();
  });

  it("shows 'Flex WR' descriptive label for WR4 when WR filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    const flexWREl = screen.getByText("Flex WR");
    expect(flexWREl.parentElement).toHaveTextContent(/WR4/);
  });

  it("shows 'Elite TE' descriptive label for TE1 when TE filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^te$/i }));
    const eliteTEEl = screen.getByText("Elite TE");
    expect(eliteTEEl.parentElement).toHaveTextContent(/TE1/);
  });

  it("shows 'Elite QB' descriptive label for QB1 when QB filter is active", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^qb$/i }));
    const eliteQBEl = screen.getByText("Elite QB");
    expect(eliteQBEl.parentElement).toHaveTextContent(/QB1/);
  });

  it("filters by position when a position chip is clicked", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Justin Jefferson")).toBeInTheDocument();
    expect(screen.queryByText("Bijan Robinson")).not.toBeInTheDocument();
    expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  });

  it("groups by positional tier when filtered to a position", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    // Now the tier headers should be position-relative (WR1, WR2) not overall (Tier 1, Tier 2).
    expect(screen.getByText(/WR1/)).toBeInTheDocument();
    expect(screen.getByText(/WR2/)).toBeInTheDocument();
  });

  it("calls onDownloadCsv when CSV button clicked", async () => {
    const onDownload = vi.fn();
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={onDownload} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^download csv$/i }));
    expect(onDownload).toHaveBeenCalled();
  });

  describe("debug CSV button", () => {
    it("is hidden when debugMode is falsy", () => {
      render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
      expect(screen.queryByRole("button", { name: /download debug csv/i })).not.toBeInTheDocument();
    });

    it("is shown when debugMode is true", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadCsv={() => {}}
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
          onDownloadCsv={() => {}}
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
          onDownloadCsv={() => {}}
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
          onDownloadCsv={() => {}}
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
          onDownloadCsv={() => {}}
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
          onDownloadCsv={() => {}}
          tierLabelOverrides={{ 1: "Studs" }}
        />,
      );
      // Tier 2 is not overridden, should show "Strong Starter"
      const starterEl = screen.getByText("Strong Starter");
      expect(starterEl.parentElement).toHaveTextContent(/Tier 2/);
    });
  });
});
