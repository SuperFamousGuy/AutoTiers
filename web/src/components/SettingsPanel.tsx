import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { RotateCcw } from "lucide-react";
import { ScoreWeights } from "./ScoreWeights";
import { LinkedLeagueChip } from "@/components/LinkedLeagueChip";
import { TIER_LABELS } from "@/lib/tiers";
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
}

interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
  linkedLeague?: { provider: "sleeper" | "espn"; leagueName: string } | null;
  profileId?: string | null;
  onRefreshLink?: () => Promise<void> | void;
}

const LEAGUE_SIZES: LeagueSize[] = [8, 10, 12, 14, 16];
const DRAFT_ROUNDS_OPTIONS = [10, 12, 14, 15, 16, 18, 20, 25] as const;
const TIER_LABEL_ROWS = [1, 2, 3, 4, 5, 6] as const;

export function SettingsPanel({ value, onChange, linkedLeague, profileId, onRefreshLink }: SettingsPanelProps) {
  const set = <K extends keyof SettingsState>(key: K, v: SettingsState[K]) =>
    onChange({ ...value, [key]: v });

  const hasAnyOverride = Object.keys(value.tier_labels ?? {}).length > 0;

  const handleTierLabelChange = (tier: number, inputValue: string) => {
    const defaultLabel = TIER_LABELS[tier];
    const trimmed = inputValue;
    // Remove key if empty or equal to the static default
    if (trimmed === "" || trimmed === defaultLabel) {
      const next = { ...(value.tier_labels ?? {}) };
      delete next[tier];
      set("tier_labels", Object.keys(next).length > 0 ? next : undefined);
    } else {
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
          ["bonus_first_downs", "First Down Bonus"],
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
      </div>

      <ScoreWeights
        weights={value.weights}
        onChange={(w) => set("weights", w)}
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Tier Labels</Label>
          {hasAnyOverride && (
            <Button variant="ghost" size="sm" onClick={handleResetAll}>
              Reset all
            </Button>
          )}
        </div>
        {TIER_LABEL_ROWS.map((tier) => {
          const hasOverride = value.tier_labels?.[tier] !== undefined;
          const defaultLabel = TIER_LABELS[tier] ?? "";
          return (
            <div key={tier} className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-12 shrink-0">Tier {tier}</span>
              <input
                type="text"
                value={value.tier_labels?.[tier] ?? ""}
                placeholder={defaultLabel}
                onChange={(e) => handleTierLabelChange(tier, e.target.value)}
                className="w-full h-8 rounded border border-input bg-background px-2 text-sm text-foreground"
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
      </div>
    </aside>
  );
}
