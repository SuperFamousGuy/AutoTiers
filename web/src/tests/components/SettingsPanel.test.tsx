import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SettingsPanel, DRAFT_ROUNDS_OPTIONS, TIER_COUNT_OPTIONS, LEAGUE_SIZES } from "@/components/SettingsPanel";
import type { SettingsState } from "@/components/SettingsPanel";
import { TIER_LABELS } from "@/lib/tiers";

const baseSettings: SettingsState = {
  scoring_format: "standard",
  league_size: 12,
  draft_rounds: 15,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weights: {
    prior: 30,
    consensus: 70,
  },
};

function StatefulPanel({ initial, onChangeSpy = vi.fn() }: { initial?: SettingsState["tier_labels"]; onChangeSpy?: ReturnType<typeof vi.fn> }) {
  const [value, setValue] = useState<SettingsState>({ ...baseSettings, tier_labels: initial });
  const handleChange = (next: SettingsState) => {
    setValue(next);
    onChangeSpy(next);
  };
  return <SettingsPanel value={value} onChange={handleChange} />;
}

describe("SettingsPanel — Tier Labels section", () => {
  it("renders inputs with correct placeholder values for all named tiers", () => {
    render(<StatefulPanel />);
    for (const [tier, label] of Object.entries(TIER_LABELS)) {
      const input = screen.getByRole("textbox", { name: `Tier ${tier} label` });
      expect(input).toHaveAttribute("placeholder", label);
    }
  });

  it("shows empty value when no override is set", () => {
    render(<StatefulPanel />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("shows stored override value in the input", () => {
    render(<StatefulPanel initial={{ 1: "Studs" }} />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    expect((input as HTMLInputElement).value).toBe("Studs");
  });

  it("typing a custom label stores it mid-type", async () => {
    const spy = vi.fn();
    render(<StatefulPanel onChangeSpy={spy} />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    const user = userEvent.setup();
    await user.type(input, "S");
    const lastCall = spy.mock.calls[spy.mock.calls.length - 1][0] as SettingsState;
    expect(lastCall.tier_labels?.[1]).toBe("S");
  });

  it("blurring with the exact static default removes the key", async () => {
    const spy = vi.fn();
    render(<StatefulPanel initial={{ 1: "Studs" }} onChangeSpy={spy} />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    const user = userEvent.setup();
    await user.clear(input);
    await user.type(input, "Elite");
    await user.tab();
    const lastCall = spy.mock.calls[spy.mock.calls.length - 1][0] as SettingsState;
    expect(lastCall.tier_labels?.[1]).toBeUndefined();
  });

  it("blurring with empty string removes the key", async () => {
    const spy = vi.fn();
    render(<StatefulPanel initial={{ 1: "Studs" }} onChangeSpy={spy} />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    const user = userEvent.setup();
    await user.clear(input);
    await user.tab();
    const lastCall = spy.mock.calls[spy.mock.calls.length - 1][0] as SettingsState;
    expect(lastCall.tier_labels?.[1]).toBeUndefined();
  });

  it("blurring with whitespace-only value removes the key", async () => {
    const spy = vi.fn();
    render(<StatefulPanel initial={{ 1: "Studs" }} onChangeSpy={spy} />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    const user = userEvent.setup();
    await user.clear(input);
    await user.type(input, "   ");
    await user.tab();
    const lastCall = spy.mock.calls[spy.mock.calls.length - 1][0] as SettingsState;
    expect(lastCall.tier_labels?.[1]).toBeUndefined();
  });

  it("per-tier reset button only renders when that tier has an override", () => {
    render(<StatefulPanel initial={{ 1: "Studs" }} />);
    expect(screen.getByRole("button", { name: "Reset tier 1 label" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reset tier 2 label" })).not.toBeInTheDocument();
  });

  it("clicking per-tier reset removes that tier's override and keeps others", async () => {
    render(<StatefulPanel initial={{ 1: "Studs", 2: "Solid" }} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reset tier 1 label" }));
    expect(screen.queryByRole("button", { name: "Reset tier 1 label" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset tier 2 label" })).toBeInTheDocument();
  });

  it("Reset all button is absent when no override exists", () => {
    render(<StatefulPanel />);
    expect(screen.queryByRole("button", { name: /reset all/i })).not.toBeInTheDocument();
  });

  it("Reset all button is present when at least one override exists", () => {
    render(<StatefulPanel initial={{ 3: "Mid" }} />);
    expect(screen.getByRole("button", { name: /reset all/i })).toBeInTheDocument();
  });

  it("clicking Reset all removes all overrides and hides the button", async () => {
    render(<StatefulPanel initial={{ 1: "Studs", 2: "Solid" }} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /reset all/i }));
    expect(screen.queryByRole("button", { name: /reset all/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reset tier/i })).not.toBeInTheDocument();
  });

  it("input does not snap to empty while typing the exact default mid-keystroke", async () => {
    render(<StatefulPanel />);
    const input = screen.getByRole("textbox", { name: "Tier 1 label" });
    const user = userEvent.setup();
    await user.type(input, "Elit");
    expect((input as HTMLInputElement).value).toBe("Elit");
  });
});

describe("SettingsPanel — tier count control", () => {
  it("number of tiers select renders with default value equal to league_size when tier_count absent", () => {
    render(<StatefulPanel />);
    // baseSettings has league_size=12 and no tier_count
    // The select should show "12 tiers"
    expect(screen.getByRole("combobox", { name: /number of tiers/i })).toBeInTheDocument();
    // The displayed value should reflect 12 (league_size fallback)
    expect(screen.getByText("12 tiers")).toBeInTheDocument();
  });

  it("renders the correct number of tier label rows based on tier_count", () => {
    const { rerender } = render(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 8 }}
        onChange={vi.fn()}
      />,
    );
    // Should render 8 rows
    for (let i = 1; i <= 8; i++) {
      expect(screen.getByRole("textbox", { name: `Tier ${i} label` })).toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox", { name: "Tier 9 label" })).not.toBeInTheDocument();

    rerender(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 4 }}
        onChange={vi.fn()}
      />,
    );
    for (let i = 1; i <= 4; i++) {
      expect(screen.getByRole("textbox", { name: `Tier ${i} label` })).toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox", { name: "Tier 5 label" })).not.toBeInTheDocument();
  });

  it("reducing tier count hides rows beyond the new count", () => {
    const { rerender } = render(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 10 }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("textbox", { name: "Tier 10 label" })).toBeInTheDocument();

    rerender(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 6 }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("textbox", { name: "Tier 7 label" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Tier 10 label" })).not.toBeInTheDocument();
  });

  it("restoring tier count reveals previously stored overrides", () => {
    const onChange = vi.fn();
    // Render with 8 tiers and an override on tier 8
    const { rerender } = render(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 8, tier_labels: { 8: "My Label" } }}
        onChange={onChange}
      />,
    );
    expect((screen.getByRole("textbox", { name: "Tier 8 label" }) as HTMLInputElement).value).toBe("My Label");

    // Reduce to 6 — tier 8 row disappears but the override is in state (external)
    rerender(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 6, tier_labels: { 8: "My Label" } }}
        onChange={onChange}
      />,
    );
    expect(screen.queryByRole("textbox", { name: "Tier 8 label" })).not.toBeInTheDocument();

    // Restore to 8 — tier 8 reappears with the same override
    rerender(
      <SettingsPanel
        value={{ ...baseSettings, tier_count: 8, tier_labels: { 8: "My Label" } }}
        onChange={onChange}
      />,
    );
    expect((screen.getByRole("textbox", { name: "Tier 8 label" }) as HTMLInputElement).value).toBe("My Label");
  });

  it("collapsible toggle hides and shows tier label rows", async () => {
    render(<StatefulPanel />);
    const user = userEvent.setup();

    // Tier rows should be present initially (open by default)
    expect(screen.getByRole("textbox", { name: "Tier 1 label" })).toBeInTheDocument();

    // Click the collapse toggle — Radix CollapsibleContent removes content from DOM
    const toggle = screen.getByRole("button", { name: /collapse tier labels/i });
    await user.click(toggle);

    // Content should be removed from DOM when collapsed
    expect(screen.queryByRole("textbox", { name: "Tier 1 label" })).not.toBeInTheDocument();

    // Click again to re-expand
    const expandToggle = screen.getByRole("button", { name: /expand tier labels/i });
    await user.click(expandToggle);
    expect(screen.getByRole("textbox", { name: "Tier 1 label" })).toBeInTheDocument();
  });

  it("reset all button is visible in collapsed header when overrides exist", async () => {
    render(<StatefulPanel initial={{ 1: "Studs" }} />);
    const user = userEvent.setup();

    // Collapse
    await user.click(screen.getByRole("button", { name: /collapse tier labels/i }));

    // Reset all should still be visible in the header even when collapsed
    expect(screen.getByRole("button", { name: /reset all/i })).toBeInTheDocument();
  });

  it("profile with league_size=16 and no tier_count shows '16 tiers' in select and renders 16 rows", () => {
    // Regression: a profile with league_size=16 and no tier_count key must not yield a
    // blank Select (effectiveTierCount = tier_count ?? league_size = 16).
    // Every league_size value must have a matching <SelectItem> in TIER_COUNT_OPTIONS.
    render(
      <SettingsPanel
        value={{ ...baseSettings, league_size: 16, tier_count: undefined }}
        onChange={vi.fn()}
      />,
    );
    // The tier-count Select should display "16 tiers" (not blank)
    expect(screen.getByText("16 tiers")).toBeInTheDocument();
    // All 16 tier-label rows should be rendered
    for (let i = 1; i <= 16; i++) {
      expect(screen.getByRole("textbox", { name: `Tier ${i} label` })).toBeInTheDocument();
    }
    // No 17th row should exist
    expect(screen.queryByRole("textbox", { name: "Tier 17 label" })).not.toBeInTheDocument();
  });

  it("TIER_COUNT_OPTIONS max >= max(LEAGUE_SIZES) (guard against blank Select regression)", () => {
    // If a new league_size is added to LEAGUE_SIZES that exceeds TIER_COUNT_OPTIONS max,
    // the tier-count Select will render blank for any profile using that league_size as fallback.
    const maxLeagueSize = Math.max(...LEAGUE_SIZES);
    const maxTierCount = Math.max(...TIER_COUNT_OPTIONS);
    expect(maxTierCount).toBeGreaterThanOrEqual(maxLeagueSize);
  });
});
