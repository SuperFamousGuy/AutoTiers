import { useState } from "react";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { RotateCcw, ChevronDown, ChevronUp } from "lucide-react";
import { ScoreWeights } from "./ScoreWeights";
import { LinkedLeagueChip } from "@/components/LinkedLeagueChip";
import { TIER_LABELS, getTierLabel } from "@/lib/tiers";
import type { ScoringFormat, LeagueSize, QbTdPoints } from "@/api/types";
import type { Weights } from "@/lib/weights";

export interface SettingsState {
  scoring_format: ScoringFormat;
  league_size: LeagueSize;
  draft_rounds: number;
  qb_td_points: QbTdPoints;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  weights: Weights;
  tier_labels?: Partial<Record<number, string>>;
  tier_count?: number;
}

interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
  linkedLeague?: { provider: "sleeper" | "espn" | "yahoo"; leagueName: string } | null;
  profileId?: string | null;
  onRefreshLink?: () => Promise<void> | void;
}

export const LEAGUE_SIZES: LeagueSize[] = [8, 10, 12, 14, 16];
export const DRAFT_ROUNDS_OPTIONS = [10, 12, 14, 15, 16, 18, 20, 25] as const;
// Must cover every value reachable via the league_size fallback (effectiveTierCount = tier_count ?? league_size).
// LEAGUE_SIZES is [8, 10, 12, 14, 16] — all within this range — enforced by the guard test in SettingsPanel.test.tsx.
export const TIER_COUNT_OPTIONS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25] as const;

export function SettingsPanel({ value, onChange, linkedLeague, profileId, onRefreshLink }: SettingsPanelProps) {
  const set = <K extends keyof SettingsState>(key: K, v: SettingsState[K]) =>
    onChange({ ...value, [key]: v });

  const [tierLabelsOpen, setTierLabelsOpen] = useState(true);

  const hasAnyOverride = Object.keys(value.tier_labels ?? {}).length > 0;

  // Effective tier count: explicit setting or fall back to league_size
  const effectiveTierCount = value.tier_count ?? value.league_size;

  const handleTierLabelChange = (tier: number, inputValue: string) => {
    set("tier_labels", { ...(value.tier_labels ?? {}), [tier]: inputValue });
  };

  const handleTierLabelBlur = (tier: number, inputValue: string) => {
    const trimmed = inputValue.trim();
    const defaultLabel = TIER_LABELS[tier] ?? getTierLabel(tier);
    if (trimmed === "" || trimmed === defaultLabel) {
      const next = { ...(value.tier_labels ?? {}) };
      delete next[tier];
      set("tier_labels", Object.keys(next).length > 0 ? next : undefined);
    } else if (trimmed !== inputValue) {
      set("tier_labels", { ...(value.tier_labels ?? {}), [tier]: trimmed });
    }
  };

  const handleResetTier = (tier: number) => {
    const next = { ...(value.tier_labels ?? {}) };
    delete next[tier];
    set("tier_labels", Object.keys(next).length > 0 ? next : undefined);
  };

  const handleResetAll = () => {
    set("tier_labels", undefined);
  };

  return (
    <aside className="space-y-6 border-r bg-card p-6 overflow-y-auto min-h-0">
      {linkedLeague && profileId && (
        <LinkedLeagueChip
          profileId={profileId}
          provider={linkedLeague.provider}
          leagueName={linkedLeague.leagueName}
          onRefreshed={async () => { await onRefreshLink?.(); }}
        />
      )}
      <h2 className="text-lg font-semibold">Settings</h2>

      <div className="space-y-2">
        <Label>Scoring Format</Label>
        <RadioGroup
          value={value.scoring_format}
          onValueChange={(v) => set("scoring_format", v as ScoringFormat)}
        >
          {([
            ["standard", "Standard"],
            ["half_ppr", "Half PPR"],
            ["ppr", "Full PPR"],
          ] as const).map(([val, label]) => (
            <div key={val} className="flex items-center gap-2">
              <RadioGroupItem value={val} id={`sf-${val}`} />
              <Label htmlFor={`sf-${val}`} className="cursor-pointer">{label}</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-2">
        <Label>League Size</Label>
        <Select
          value={String(value.league_size)}
          onValueChange={(v) => set("league_size", Number(v) as LeagueSize)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAGUE_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>{n} teams</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Draft Rounds</Label>
        <Select
          value={String(value.draft_rounds)}
          onValueChange={(v) => set("draft_rounds", Number(v))}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DRAFT_ROUNDS_OPTIONS.map((n) => (
              <SelectItem key={n} value={String(n)}>{n} rounds</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>QB Passing TDs</Label>
        <RadioGroup
          value={String(value.qb_td_points)}
          onValueChange={(v) => set("qb_td_points", Number(v) as QbTdPoints)}
          className="flex gap-4"
        >
          {([4, 6] as const).map((n) => (
            <div key={n} className="flex items-center gap-2">
              <RadioGroupItem value={String(n)} id={`qb-${n}`} />
              <Label htmlFor={`qb-${n}`} className="cursor-pointer">{n} pts</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-3">
        <Label>Bonuses</Label>
        {([
          ["bonus_100yd_rushing", "100-yd Rushing"],
          ["bonus_100yd_receiving", "100-yd Receiving"],
        ] as const).map(([key, label]) => (
          <div key={key} className="flex items-center justify-between">
            <Label htmlFor={key} className="cursor-pointer">{label}</Label>
            <Switch
              id={key}
              checked={value[key]}
              onCheckedChange={(v) => set(key, v)}
            />
          </div>
        ))}
        <div className="flex items-center justify-between opacity-50">
          <div className="space-y-0.5">
            <Label htmlFor="bonus_first_downs" className="cursor-not-allowed">First Down Bonus</Label>
            <p className="text-xs text-muted-foreground">Coming soon</p>
          </div>
          <Switch
            id="bonus_first_downs"
            checked={value.bonus_first_downs}
            onCheckedChange={() => undefined}
            disabled
            aria-disabled="true"
          />
        </div>
      </div>

      <ScoreWeights
        weights={value.weights}
        onChange={(w) => set("weights", w)}
      />

      <Collapsible open={tierLabelsOpen} onOpenChange={setTierLabelsOpen}>
        <div className="flex items-center justify-between">
          <Label>Tier Labels</Label>
          <div className="flex items-center gap-1">
            {hasAnyOverride && (
              <Button variant="ghost" size="sm" onClick={handleResetAll}>
                Reset all
              </Button>
            )}
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label={tierLabelsOpen ? "Collapse tier labels" : "Expand tier labels"}
              >
                {tierLabelsOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
          </div>
        </div>
        <CollapsibleContent className="space-y-3 mt-3">
          <div className="space-y-2">
            <Label htmlFor="tier-count-select">Number of Tiers</Label>
            <Select
              value={String(effectiveTierCount)}
              onValueChange={(v) => set("tier_count", Number(v))}
            >
              <SelectTrigger id="tier-count-select" aria-label="Number of Tiers">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIER_COUNT_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n} tiers</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {Array.from({ length: effectiveTierCount }, (_, i) => i + 1).map((tier) => {
            const hasOverride = value.tier_labels?.[tier] !== undefined;
            const defaultLabel = getTierLabel(tier);
            return (
              <div key={tier} className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground w-12 shrink-0">Tier {tier}</span>
                <Input
                  type="text"
                  value={value.tier_labels?.[tier] ?? ""}
                  placeholder={defaultLabel}
                  onChange={(e) => handleTierLabelChange(tier, e.target.value)}
                  onBlur={(e) => handleTierLabelBlur(tier, e.target.value)}
                  className="h-8"
                  aria-label={`Tier ${tier} label`}
                />
                {hasOverride && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Reset tier ${tier} label`}
                    onClick={() => handleResetTier(tier)}
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                )}
              </div>
            );
          })}
        </CollapsibleContent>
      </Collapsible>
    </aside>
  );
}
