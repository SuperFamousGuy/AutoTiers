import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScoreWeights } from "./ScoreWeights";
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
}

interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
}

const LEAGUE_SIZES: LeagueSize[] = [8, 10, 12, 14, 16];
const DRAFT_ROUNDS_OPTIONS = [10, 12, 14, 15, 16, 18, 20, 25] as const;

export function SettingsPanel({ value, onChange }: SettingsPanelProps) {
  const set = <K extends keyof SettingsState>(key: K, v: SettingsState[K]) =>
    onChange({ ...value, [key]: v });

  return (
    <aside className="space-y-6 border-r bg-card p-6 overflow-y-auto min-h-0">
      <h2 className="text-lg font-semibold">Settings</h2>

      <div className="space-y-2">
        <Label>Scoring format</Label>
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
        <Label>League size</Label>
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
        <Label>Draft rounds</Label>
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
        <Label>QB passing TDs</Label>
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
          ["bonus_100yd_rushing", "100-yd rushing"],
          ["bonus_100yd_receiving", "100-yd receiving"],
          ["bonus_first_downs", "First down bonus"],
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
    </aside>
  );
}
