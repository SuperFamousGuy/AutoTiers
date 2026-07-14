import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TiersPanel } from "@/components/TiersPanel";
import { ApiError } from "@/api/client";
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

const qbOnlyResponse: GenerateResponse = {
  total: 1,
  data_as_of: null,
  players: [
    {
      overall_rank: 1,
      player_id: "1001",
      name: "Solo Quarterback",
      position: "QB",
      team: "KC",
      age: null,
      overall_tier: 1,
      positional_tier: "QB1",
      adjusted_score: 90.0,
      projected_score_raw: 90.0,
      prior_year_actual: null,
      espn_projection: null,
      fantasypros_projection: null,
      avg_projection: null,
      adp_standard: null,
      adp_ppr: null,
      adp_dynasty: null,
      league_adp: null,
      vbd_score: 0.0,
      position_replacement: 90.0,
      flags: [],
      rules_applied: [],
      rule_applications: [],
      is_favorite_player: null,
      is_favorite_team: null,
    },
  ],
};

const emptyResponse: GenerateResponse = {
  total: 0,
  data_as_of: null,
  players: [],
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

  describe("generate error state (#607)", () => {
    it("renders a role=alert error affordance — distinct from the empty state — when isError is true", () => {
      render(
        <TiersPanel
          result={null}
          isPending={false}
          isError={true}
          error={new ApiError(500, "boom")}
          onDownloadXlsx={() => {}}
        />,
      );

      // Announced as an alert, names the failure, and does NOT masquerade as the
      // pre-generate empty state.
      const alert = screen.getByRole("alert");
      expect(within(alert).getByText(/couldn't generate your tier list/i)).toBeInTheDocument();
      expect(screen.queryByText(/click generate to build/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/generating tier list/i)).not.toBeInTheDocument();
    });

    it("describes the specific failure (a 5xx) rather than showing a bare error", () => {
      render(
        <TiersPanel
          result={null}
          isPending={false}
          isError={true}
          error={new ApiError(503, "upstream timeout")}
          onDownloadXlsx={() => {}}
        />,
      );
      expect(screen.getByText(/the server ran into a problem/i)).toBeInTheDocument();
    });

    it("takes precedence over the empty state even when result is null", () => {
      render(
        <TiersPanel result={null} isPending={false} isError={true} onDownloadXlsx={() => {}} />,
      );
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.queryByText(/click generate to build/i)).not.toBeInTheDocument();
    });

    it("Retry re-fires the same request via onRegenerate", async () => {
      const onRegenerate = vi.fn();
      render(
        <TiersPanel
          result={null}
          isPending={false}
          isError={true}
          error={new ApiError(500, "boom")}
          onRegenerate={onRegenerate}
          canRegenerate={true}
          onDownloadXlsx={() => {}}
        />,
      );
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: /^retry$/i }));
      expect(onRegenerate).toHaveBeenCalledTimes(1);
    });

    it("disables Retry when canRegenerate is false (e.g. weights became invalid)", () => {
      render(
        <TiersPanel
          result={null}
          isPending={false}
          isError={true}
          error={new ApiError(500, "boom")}
          onRegenerate={() => {}}
          canRegenerate={false}
          onDownloadXlsx={() => {}}
        />,
      );
      expect(screen.getByRole("button", { name: /^retry$/i })).toBeDisabled();
    });

    it("a pending retry shows the spinner, not the error state", () => {
      // isPending wins over isError so the in-flight retry reads as 'working',
      // not 'still broken'.
      render(
        <TiersPanel
          result={null}
          isPending={true}
          isError={true}
          error={new ApiError(500, "boom")}
          onDownloadXlsx={() => {}}
        />,
      );
      expect(screen.getByText(/generating tier list/i)).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
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

  describe("Excel export busy/error state (#647)", () => {
    // A controllable deferred so the test can hold the export "in flight" and
    // assert the busy affordances before resolving/rejecting it.
    function deferred() {
      let resolve!: () => void;
      let reject!: (reason?: unknown) => void;
      const promise = new Promise<void>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      return { promise, resolve, reject };
    }

    it("disables the button and shows a spinner while the export is pending", async () => {
      const d = deferred();
      const onDownload = vi.fn(() => d.promise);
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={onDownload} />);
      const user = userEvent.setup();

      const button = screen.getByRole("button", { name: /^download excel$/i });
      await user.click(button);

      // In flight: button disabled, marked busy, and the pending state announced.
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("status")).toHaveTextContent(/building the excel file/i);

      // Resolving the export returns the button to its idle, clickable state.
      d.resolve();
      await waitFor(() => expect(button).not.toBeDisabled());
      expect(button).toHaveAttribute("aria-busy", "false");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("surfaces a named inline error with a Retry when the export rejects", async () => {
      const d = deferred();
      const onDownload = vi.fn(() => d.promise);
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={onDownload} />);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: /^download excel$/i }));
      d.reject(new Error("chunk load failed"));

      const alert = await screen.findByRole("alert");
      expect(within(alert).getByText(/couldn't build the excel file/i)).toBeInTheDocument();
      expect(within(alert).getByRole("button", { name: /^retry$/i })).toBeInTheDocument();
      // The button is no longer busy — the user can act again.
      expect(screen.getByRole("button", { name: /^download excel$/i })).not.toBeDisabled();
    });

    it("Retry re-fires the export and clears the error on success", async () => {
      const first = deferred();
      const second = deferred();
      const onDownload = vi
        .fn()
        .mockReturnValueOnce(first.promise)
        .mockReturnValueOnce(second.promise);
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={onDownload} />);
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: /^download excel$/i }));
      first.reject(new Error("offline"));
      const retry = await screen.findByRole("button", { name: /^retry$/i });

      await user.click(retry);
      second.resolve();

      await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
      expect(onDownload).toHaveBeenCalledTimes(2);
    });

    it("leaves the synchronous Debug CSV button unaffected while an export is pending", async () => {
      const d = deferred();
      const onDownload = vi.fn(() => d.promise);
      const onDebug = vi.fn();
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={onDownload}
          debugMode={true}
          onDownloadDebugCsv={onDebug}
        />,
      );
      const user = userEvent.setup();

      await user.click(screen.getByRole("button", { name: /^download excel$/i }));

      // The Excel button is busy, but the CSV button stays enabled and clickable.
      const csvButton = screen.getByRole("button", { name: /download debug csv/i });
      expect(csvButton).not.toBeDisabled();
      await user.click(csvButton);
      expect(onDebug).toHaveBeenCalledTimes(1);
    });
  });

  describe("empty position filter", () => {
    it("shows an empty-state message and reset button when the selected position has no players", async () => {
      render(<TiersPanel result={qbOnlyResponse} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();

      // Filtering to DST — a position absent from this QB-only list — must not
      // leave a blank scroll area behind the filter row.
      await user.click(screen.getByRole("button", { name: /^dst$/i }));

      expect(screen.getByText(/no dst players in this tier list/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /show all positions/i })).toBeInTheDocument();
      // The QB tier group must be gone while DST is selected.
      expect(screen.queryByText("Solo Quarterback")).not.toBeInTheDocument();
    });

    it("clicking 'Show all positions' resets to ALL and repopulates the list", async () => {
      render(<TiersPanel result={qbOnlyResponse} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: /^dst$/i }));
      expect(screen.getByText(/no dst players in this tier list/i)).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /show all positions/i }));

      // Back to the ALL view: the QB player and its overall tier group reappear,
      // and the empty-state message is gone.
      expect(screen.queryByText(/no dst players in this tier list/i)).not.toBeInTheDocument();
      expect(screen.getByText("Solo Quarterback")).toBeInTheDocument();
      expect(screen.getByText(/^Tier 1$/)).toBeInTheDocument();
    });

    it("does not show the empty-state message in the ALL view even when a list is empty", () => {
      // The guard only fires for a position filter, never for ALL — an empty ALL
      // list is a different (upstream) condition and keeps the existing render path.
      // Render a genuinely empty players list under the default ALL filter so the
      // assertion actually exercises the `filter === "ALL"` branch of the guard:
      // groupedByTier is empty here, yet the empty-state message must stay hidden.
      render(<TiersPanel result={emptyResponse} isPending={false} onDownloadXlsx={() => {}} />);
      expect(screen.queryByText(/players in this tier list/i)).not.toBeInTheDocument();
    });
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

  describe("staleness banner", () => {
    const STALE_TEXT = /settings changed since this list was generated/i;

    it("does not show the banner when isStale is falsy (default)", () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();
    });

    it("does not show the banner before the first generate (empty state)", () => {
      render(<TiersPanel result={null} isPending={false} onDownloadXlsx={() => {}} isStale={true} />);
      expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();
      // Empty-state copy still shows.
      expect(screen.getByText(/click generate/i)).toBeInTheDocument();
    });

    it("does not show the banner while a (re)generate is pending", () => {
      render(<TiersPanel result={null} isPending={true} onDownloadXlsx={() => {}} isStale={true} />);
      expect(screen.queryByText(STALE_TEXT)).not.toBeInTheDocument();
      expect(screen.getByText(/generating/i)).toBeInTheDocument();
    });

    it("shows the banner when isStale is true and a result exists", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          isStale={true}
          canRegenerate={true}
        />,
      );
      expect(screen.getByText(STALE_TEXT)).toBeInTheDocument();
    });

    it("calls onRegenerate when the banner's Generate button is clicked", async () => {
      const onRegenerate = vi.fn();
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          isStale={true}
          canRegenerate={true}
          onRegenerate={onRegenerate}
        />,
      );
      const banner = screen.getByRole("status");
      const user = userEvent.setup();
      await user.click(within(banner).getByRole("button", { name: /^generate$/i }));
      expect(onRegenerate).toHaveBeenCalledTimes(1);
    });

    it("disables the banner's Generate button when canRegenerate is false", () => {
      render(
        <TiersPanel
          result={response}
          isPending={false}
          onDownloadXlsx={() => {}}
          isStale={true}
          canRegenerate={false}
        />,
      );
      const banner = screen.getByRole("status");
      expect(within(banner).getByRole("button", { name: /^generate$/i })).toBeDisabled();
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

    it("Reset Draft clears all drafted players once the confirmation is accepted", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
      try {
        render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
        const user = userEvent.setup();
        await user.click(screen.getByRole("switch", { name: /draft mode/i }));
        await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
        await user.click(screen.getByRole("button", { name: /mark bijan robinson as drafted/i }));
        expect(screen.getByText(/2 drafted/i)).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /^reset draft$/i }));

        // The confirmation names the count of players about to be wiped.
        expect(confirmSpy).toHaveBeenCalledWith(
          expect.stringMatching(/clear all 2 drafted players for this board\? this can't be undone\./i),
        );
        // Header suffix now reads "0 drafted" (still in Draft Mode), not "2 drafted".
        expect(screen.getByText(/0 drafted/i)).toBeInTheDocument();
        expect(screen.queryByText(/2 drafted/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /mark bijan robinson as drafted/i })).toBeInTheDocument();
      } finally {
        confirmSpy.mockRestore();
      }
    });

    it("Reset Draft keeps the drafted players when the confirmation is cancelled", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
      try {
        render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
        const user = userEvent.setup();
        await user.click(screen.getByRole("switch", { name: /draft mode/i }));
        await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
        await user.click(screen.getByRole("button", { name: /mark bijan robinson as drafted/i }));
        expect(screen.getByText(/2 drafted/i)).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /^reset draft$/i }));

        expect(confirmSpy).toHaveBeenCalledTimes(1);
        // Cancelling leaves the board untouched — the picks survive. Drafting
        // both of Tier 1's players auto-collapses that tier (#666), so confirm
        // the picks persisted via the count and the Drafted section rather than
        // the now-hidden player rows.
        expect(screen.getByText(/2 drafted/i)).toBeInTheDocument();
        const draftedSection = screen.getByText("Drafted (2)").closest("details")!;
        expect(within(draftedSection).getByText("Ja'Marr Chase")).toBeInTheDocument();
        expect(within(draftedSection).getByText("Bijan Robinson")).toBeInTheDocument();
      } finally {
        confirmSpy.mockRestore();
      }
    });

    it("Reset Draft with nothing drafted no-ops without prompting for confirmation", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
      try {
        render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
        const user = userEvent.setup();
        await user.click(screen.getByRole("switch", { name: /draft mode/i }));
        expect(screen.getByText(/0 drafted/i)).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /^reset draft$/i }));

        // Nothing to lose → no confirmation dialog, no state change.
        expect(confirmSpy).not.toHaveBeenCalled();
        expect(screen.getByText(/0 drafted/i)).toBeInTheDocument();
      } finally {
        confirmSpy.mockRestore();
      }
    });

    it("the Reset Draft confirmation copy is singular when exactly one player is drafted", async () => {
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
      try {
        render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
        const user = userEvent.setup();
        await user.click(screen.getByRole("switch", { name: /draft mode/i }));
        await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));

        await user.click(screen.getByRole("button", { name: /^reset draft$/i }));

        expect(confirmSpy).toHaveBeenCalledWith(
          expect.stringMatching(/clear all 1 drafted player for this board\?/i),
        );
      } finally {
        confirmSpy.mockRestore();
      }
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

  describe("auto-collapse fully-drafted tiers (#666)", () => {
    const draftTier1 = async (user: ReturnType<typeof userEvent.setup>) => {
      // Tier 1 in the fixture is Ja'Marr Chase + Bijan Robinson — draft both to
      // empty the tier of available players.
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));
      await user.click(screen.getByRole("button", { name: /mark bijan robinson as drafted/i }));
    };

    it("shows no tier collapse affordance when Draft Mode is off", () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      // The tier header is plain, non-interactive text with no expand/collapse control.
      expect(
        screen.queryByRole("button", { name: /(collapse|expand) tier 1/i }),
      ).not.toBeInTheDocument();
    });

    it("makes each tier header a collapse toggle exposing aria-expanded once Draft Mode is on", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));

      const header = screen.getByRole("button", { name: /collapse tier 1/i });
      // Tiers with available players start expanded.
      expect(header).toHaveAttribute("aria-expanded", "true");
    });

    it("auto-collapses a tier once its last available player is drafted", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await draftTier1(user);

      // Header now advertises the collapsed state...
      const header = screen.getByRole("button", { name: /expand tier 1/i });
      expect(header).toHaveAttribute("aria-expanded", "false");
      // ...and the dead drafted rows are removed from the tier so they stop
      // pushing the next available tier off-screen.
      expect(
        screen.queryByRole("button", { name: /mark ja'marr chase as available/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /mark bijan robinson as available/i }),
      ).not.toBeInTheDocument();
    });

    it("keeps a tier with remaining available players expanded", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));

      // Draft only one of Tier 1's two players — one is still available.
      await user.click(screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }));

      expect(screen.getByRole("button", { name: /collapse tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(
        screen.getByRole("button", { name: /mark bijan robinson as drafted/i }),
      ).toBeInTheDocument();
    });

    it("auto-expands a collapsed tier when a player is undrafted back into it", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await draftTier1(user);
      expect(screen.getByRole("button", { name: /expand tier 1/i })).toBeInTheDocument();

      // The rows are hidden, so undraft via the collapsible Drafted section.
      const draftedSection = screen.getByText(/^Drafted \(/).closest("details")!;
      await user.click(within(draftedSection).getByText("Ja'Marr Chase"));

      // Tier re-expands and the reinstated player's row is visible again.
      expect(screen.getByRole("button", { name: /collapse tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(
        screen.getByRole("button", { name: /mark ja'marr chase as drafted/i }),
      ).toBeInTheDocument();
    });

    it("lets the user manually expand an auto-collapsed tier via the header toggle", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));
      await draftTier1(user);

      await user.click(screen.getByRole("button", { name: /expand tier 1/i }));

      // Manual expand reveals the (drafted) rows without changing draft state.
      expect(screen.getByRole("button", { name: /collapse tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expect(
        screen.getByRole("button", { name: /mark ja'marr chase as available/i }),
      ).toBeInTheDocument();
    });

    it("resets collapse state when Draft Mode is turned off and on again", async () => {
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      const toggle = screen.getByRole("switch", { name: /draft mode/i });
      await user.click(toggle);
      await draftTier1(user);

      // Manually override the auto-collapse to expanded...
      await user.click(screen.getByRole("button", { name: /expand tier 1/i }));
      expect(screen.getByRole("button", { name: /collapse tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "true",
      );

      // ...then leave and re-enter Draft Mode. The manual override is forgotten
      // and the still-fully-drafted tier auto-collapses again.
      await user.click(toggle); // off
      await user.click(toggle); // on
      expect(screen.getByRole("button", { name: /expand tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "false",
      );
    });

    it("auto-collapses an already-fully-drafted tier the moment Draft Mode is switched on", async () => {
      // Seed a persisted board where all of Tier 1 is already drafted, then
      // enter Draft Mode — the tier should come up collapsed with no toggling.
      // Persist Draft Mode explicitly off so the board starts off (drafted
      // picks with no flag would otherwise default on via the legacy path, #707)
      // and the click below is what switches it on.
      localStorage.setItem(
        "autotiers_draft:default:standard",
        JSON.stringify(["6794", "8112"]),
      );
      localStorage.setItem("autotiers_draft_mode:default:standard", "false");
      render(<TiersPanel result={response} isPending={false} onDownloadXlsx={() => {}} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole("switch", { name: /draft mode/i }));

      expect(screen.getByRole("button", { name: /expand tier 1/i })).toHaveAttribute(
        "aria-expanded",
        "false",
      );
    });
  });
});
