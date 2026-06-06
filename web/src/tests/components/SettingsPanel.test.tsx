import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SettingsPanel } from "@/components/SettingsPanel";
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
    weight_prior_year: 0.3,
    weight_espn: 0,
    weight_consensus: 0.7,
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
  it("renders six inputs with correct placeholder values", () => {
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
