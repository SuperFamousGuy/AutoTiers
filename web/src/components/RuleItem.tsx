import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Rule } from "@/api/types";

interface RuleItemProps {
  rule: Rule;
  onChange: (next: Rule) => void;
}

const WEIGHT_VALUES = ["0.5", "1.0", "2.0"] as const;
const WEIGHT_LABELS: Record<(typeof WEIGHT_VALUES)[number], string> = {
  "0.5": "low",
  "1.0": "default",
  "2.0": "high",
};

export function RuleItem({ rule, onChange }: RuleItemProps) {
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => onChange({ ...rule, enabled: v })}
        />
        <span className="text-sm truncate">{rule.name}</span>
      </div>
      <ToggleGroup
        type="single"
        value={rule.weight.toFixed(1)}
        onValueChange={(v) => {
          if (v) onChange({ ...rule, weight: Number(v) });
        }}
        disabled={!rule.enabled}
      >
        {WEIGHT_VALUES.map((w) => (
          <ToggleGroupItem key={w} value={w} aria-label={WEIGHT_LABELS[w]}>
            {WEIGHT_LABELS[w]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
