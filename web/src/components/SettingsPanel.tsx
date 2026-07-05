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
import { getTierLabel, getCustomTierLabel } from "@/lib/tiers";
import type { TierLabelOverrides, TierLabelsByFormat } from "@/lib/tiers";
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
  // TE Premium (#525): bonus points per tight-end reception, additive on top of
  // the PPR/half-PPR value. Optional — omitted profiles use the backend default 0.0.
  te_premium_bonus?: number;
  weights: Weights;
  tier_labels?: TierLabelOverrides;
  // Per-scoring-format tier label overrides (#164). When the active scoring
  // format has an entry here, it takes precedence over the global tier_labels;
  // formats absent here fall back to tier_labels and then the static defaults.
  tier_labels_by_format?: TierLabelsByFormat;
  tier_count?: number;
  // Prior-year injury discount (#315). full_season_games is the games threshold
  // below which last season's total is treated as injury-shortened; prior_year_ramp
  // picks the discount curve. Optional — omitted profiles use the backend defaults.
  full_season_games?: number;
  prior_year_ramp?: "linear" | "steep";
}

interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
  linkedLeague?: { provider: "sleeper" | "espn" | "yahoo" | "cbs" | "nfl"; leagueName: string } | null;
  profileId?: string | null;
  onRefreshLink?: () => Promise<void> | void;
}

// Scope of the Tier Labels editor (#164): the global set, or one scoring format.
type TierLabelScope = "global" | ScoringFormat;

// Scoring formats offered in the per-format Tier Labels editor, with their
// display names. Order and labels mirror the Scoring Format radio group above.
export const SCORING_FORMAT_OPTIONS: readonly [ScoringFormat, string][] = [
  ["standard", "Standard"],
  ["half_ppr", "Half PPR"],
  ["ppr", "Full PPR"],
];

export const LEAGUE_SIZES: LeagueSize[] = [8, 10, 12, 14, 16];
export const DRAFT_ROUNDS_OPTIONS = [10, 12, 14, 15, 16, 18, 20, 25] as const;
// Must cover every value reachable via the league_size fallback (effectiveTierCount = tier_count ?? league_size).
// LEAGUE_SIZES is [8, 10, 12, 14, 16] — all within this range — enforced by the guard test in SettingsPanel.test.tsx.
export const TIER_COUNT_OPTIONS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25] as const;
// Games-played threshold for the prior-year injury discount (#315). Backend
// validates [1, 17]; we offer the realistic full-season range. Default 14.
export const FULL_SEASON_GAMES_OPTIONS = [10, 11, 12, 13, 14, 15, 16, 17] as const;
export const DEFAULT_FULL_SEASON_GAMES = 14;
export const DEFAULT_PRIOR_YEAR_RAMP = "linear" as const;
// TE Premium bonus per tight-end reception (#525). Backend validates [0.0, 2.0];
// we offer the common TEP steps. 0 = off (default).
export const TE_PREMIUM_OPTIONS = [0, 0.5, 1, 1.5, 2] as const;
export const DEFAULT_TE_PREMIUM = 0;

export function SettingsPanel({ value, onChange, linkedLeague, profileId, onRefreshLink }: SettingsPanelProps) {
  const set = <K extends keyof SettingsState>(key: K, v: SettingsState[K]) =>
    onChange({ ...value, [key]: v });

  const [tierLabelsOpen, setTierLabelsOpen] = useState(true);

  // Which label set the user is editing: the global set (all formats) or a
  // single scoring format's per-format overrides (#164).
  const [editScope, setEditScope] = useState<TierLabelScope>("global");

  // The override map currently being edited, given the selected scope.
  const currentMap: TierLabelOverrides =
    editScope === "global"
      ? value.tier_labels ?? {}
      : value.tier_labels_by_format?.[editScope] ?? {};

  const hasAnyOverride = Object.keys(currentMap).length > 0;

  // The fallback shown as each input's placeholder and used to detect a "reset
  // to default" on blur. Global edits fall back to the static default; per-format
  // edits fall back to the global override (if any), then the static default.
  const fallbackLabel = (tier: number): string =>
    editScope === "global"
      ? getTierLabel(tier)
      : getCustomTierLabel(tier, value.tier_labels);

  // Effective tier count: explicit setting or fall back to league_size
  const effectiveTierCount = value.tier_count ?? value.league_size;

  // Writes the edited map back to the right slice of settings for the current
  // scope, collapsing empty maps to `undefined` so the persisted blob stays lean.
  const setCurrentMap = (next: TierLabelOverrides | undefined) => {
    const cleaned = next && Object.keys(next).length > 0 ? next : undefined;
    if (editScope === "global") {
      set("tier_labels", cleaned);
      return;
    }
    const byFormat: TierLabelsByFormat = { ...(value.tier_labels_by_format ?? {}) };
    if (cleaned) {
      byFormat[editScope] = cleaned;
    } else {
      delete byFormat[editScope];
    }
    set("tier_labels_by_format", Object.keys(byFormat).length > 0 ? byFormat : undefined);
  };

  const handleTierLabelChange = (tier: number, inputValue: string) => {
    setCurrentMap({ ...currentMap, [tier]: inputValue });
  };

  const handleTierLabelBlur = (tier: number, inputValue: string) => {
    const trimmed = inputValue.trim();
    if (trimmed === "" || trimmed === fallbackLabel(tier)) {
      const next = { ...currentMap };
      delete next[tier];
      setCurrentMap(next);
    } else if (trimmed !== inputValue) {
      setCurrentMap({ ...currentMap, [tier]: trimmed });
    }
  };

  const handleResetTier = (tier: number) => {
    const next = { ...currentMap };
    delete next[tier];
    setCurrentMap(next);
  };

  const handleResetAll = () => {
    setCurrentMap(undefined);
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
          {SCORING_FORMAT_OPTIONS.map(([val, label]) => (
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
            disabled
            aria-disabled="true"
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="space-y-0.5">
          <Label htmlFor="te-premium-select">TE Premium</Label>
          <p className="text-xs text-muted-foreground">
            Bonus points per tight-end reception, added on top of your PPR value.
          </p>
        </div>
        <Select
          value={String(value.te_premium_bonus ?? DEFAULT_TE_PREMIUM)}
          onValueChange={(v) => set("te_premium_bonus", Number(v))}
        >
          <SelectTrigger id="te-premium-select" aria-label="TE Premium">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TE_PREMIUM_OPTIONS.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n === 0 ? "None" : `+${n.toFixed(1)} / reception`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-3">
        <div className="space-y-0.5">
          <Label>Prior-Year Injury Discount</Label>
          <p className="text-xs text-muted-foreground">
            Down-weights last season for players who missed games. Tune the
            full-season threshold and how aggressively short seasons are discounted.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="full-season-games-select">Full Season Games</Label>
          <Select
            value={String(value.full_season_games ?? DEFAULT_FULL_SEASON_GAMES)}
            onValueChange={(v) => set("full_season_games", Number(v))}
          >
            <SelectTrigger id="full-season-games-select" aria-label="Full Season Games">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FULL_SEASON_GAMES_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>{n} games</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Discount Ramp</Label>
          <RadioGroup
            value={value.prior_year_ramp ?? DEFAULT_PRIOR_YEAR_RAMP}
            onValueChange={(v) => set("prior_year_ramp", v as "linear" | "steep")}
            className="flex gap-4"
          >
            {([
              ["linear", "Linear"],
              ["steep", "Steep"],
            ] as const).map(([val, label]) => (
              <div key={val} className="flex items-center gap-2">
                <RadioGroupItem value={val} id={`ramp-${val}`} />
                <Label htmlFor={`ramp-${val}`} className="cursor-pointer">{label}</Label>
              </div>
            ))}
          </RadioGroup>
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
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetAll}
                aria-label={editScope === "global" ? "Reset all tier labels" : "Reset all tier labels for this format"}
              >
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
          <div className="space-y-2">
            <Label htmlFor="tier-label-scope-select">Editing labels for</Label>
            <Select
              value={editScope}
              onValueChange={(v) => setEditScope(v as TierLabelScope)}
            >
              <SelectTrigger id="tier-label-scope-select" aria-label="Editing labels for">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">All formats (global)</SelectItem>
                {SCORING_FORMAT_OPTIONS.map(([val, label]) => (
                  <SelectItem key={val} value={val}>{label} only</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {editScope === "global"
                ? "Applies to every scoring format unless overridden below."
                : "Overrides the global labels for this format only. Empty fields fall back to your global labels."}
            </p>
          </div>
          {Array.from({ length: effectiveTierCount }, (_, i) => i + 1).map((tier) => {
            const hasOverride = currentMap[tier] !== undefined;
            const defaultLabel = fallbackLabel(tier);
            return (
              <div key={tier} className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground w-12 shrink-0">Tier {tier}</span>
                <Input
                  type="text"
                  value={currentMap[tier] ?? ""}
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
