import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LeagueImportSummary } from "@/components/LeagueImportSummary";
import type { Profile } from "@/api/types";

type Linked = NonNullable<Profile["linked_league"]>;

const base: Linked = {
  profile_id: "p1",
  provider: "sleeper",
  league_id: "L1",
  league_metadata_json: { name: "Best League", season: 2026 },
  keepers_json: [],
  adp_json: null,
  last_synced_at: "2026-06-01T00:00:00Z",
};

function keeper(name: string) {
  return { player_name: name, position: "WR", team: "MIN" };
}

describe("LeagueImportSummary", () => {
  it("states the explicit zero-keeper case rather than omitting it", () => {
    render(<LeagueImportSummary linked={{ ...base, keepers_json: [] }} />);
    expect(screen.getByText(/No keepers detected/)).toBeInTheDocument();
  });

  it("treats a null keepers_json as zero keepers", () => {
    render(<LeagueImportSummary linked={{ ...base, keepers_json: null }} />);
    expect(screen.getByText(/No keepers detected/)).toBeInTheDocument();
  });

  it("uses the singular noun for exactly one keeper", () => {
    render(<LeagueImportSummary linked={{ ...base, keepers_json: [keeper("A")] }} />);
    expect(screen.getByText(/1 keeper detected/)).toBeInTheDocument();
    expect(screen.queryByText(/1 keepers/)).not.toBeInTheDocument();
  });

  it("pluralizes for more than one keeper and reports the count", () => {
    render(
      <LeagueImportSummary
        linked={{ ...base, keepers_json: [keeper("A"), keeper("B"), keeper("C")] }}
      />,
    );
    expect(screen.getByText(/3 keepers detected/)).toBeInTheDocument();
  });

  it("reports league ADP as available when adp_json has entries", () => {
    render(<LeagueImportSummary linked={{ ...base, adp_json: { "Justin Jefferson": 1.0 } }} />);
    expect(screen.getByText(/League ADP available/)).toBeInTheDocument();
  });

  it("reports no ADP for a null adp_json", () => {
    render(<LeagueImportSummary linked={{ ...base, adp_json: null }} />);
    expect(screen.getByText(/No ADP data for this league/)).toBeInTheDocument();
  });

  it("reports no ADP for an empty adp_json object, not 'available'", () => {
    render(<LeagueImportSummary linked={{ ...base, adp_json: {} }} />);
    expect(screen.getByText(/No ADP data for this league/)).toBeInTheDocument();
    expect(screen.queryByText(/League ADP available/)).not.toBeInTheDocument();
  });

  it("combines both facts on a single line", () => {
    render(
      <LeagueImportSummary
        linked={{ ...base, keepers_json: [keeper("A")], adp_json: { "A": 1 } }}
      />,
    );
    expect(screen.getByText("1 keeper detected · League ADP available")).toBeInTheDocument();
  });

  it.each(["yahoo", "nfl"] as const)(
    "renders neutral 'not available' copy for %s regardless of keepers_json/adp_json content",
    (provider) => {
      // Yahoo/NFL backends hard-code keepers=[]/adp_json=None and never query
      // detection, so even a populated payload must not produce an assertive
      // negative — and never the assertive negatives at all.
      const { rerender } = render(
        <LeagueImportSummary
          linked={{ ...base, provider, keepers_json: [], adp_json: null }}
        />,
      );
      expect(
        screen.getByText(/Keeper detection isn't available for .* leagues yet/),
      ).toBeInTheDocument();
      expect(screen.getByText(/League ADP isn't available for .* leagues yet/)).toBeInTheDocument();
      expect(screen.queryByText(/No keepers detected/)).not.toBeInTheDocument();
      expect(screen.queryByText(/No ADP data for this league/)).not.toBeInTheDocument();

      // A populated payload doesn't flip it to an assertive detected/available
      // claim either — the backend never populates these for Yahoo/NFL.
      rerender(
        <LeagueImportSummary
          linked={{
            ...base,
            provider,
            keepers_json: [keeper("A")],
            adp_json: { A: 1 },
          }}
        />,
      );
      expect(
        screen.getByText(/Keeper detection isn't available for .* leagues yet/),
      ).toBeInTheDocument();
      expect(screen.queryByText(/keeper detected/)).not.toBeInTheDocument();
      expect(screen.queryByText(/League ADP available/)).not.toBeInTheDocument();
    },
  );

  it("names the provider in the not-available copy", () => {
    render(<LeagueImportSummary linked={{ ...base, provider: "yahoo" }} />);
    expect(screen.getByText(/Yahoo leagues yet/)).toBeInTheDocument();
  });

  it("renders nothing when no league is linked (account-only link)", () => {
    const { container } = render(
      <LeagueImportSummary
        linked={{
          ...base,
          league_id: null,
          league_metadata_json: null,
          keepers_json: null,
          adp_json: null,
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
