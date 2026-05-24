import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";
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

function computeImpact(rule: Rule): { low: string; default: string; high: string } | null {
  const { type, value } = rule.effect;

  if (type === "flag") return null;  // flag rules don't appear in this panel anyway

  if (type === "multiplier") {
    const distance = Number(value) - 1.0;
    const calc = (weight: number) => {
      const pct = distance * weight * 100;
      const sign = pct >= 0 ? "+" : "";
      return `${sign}${pct.toFixed(1)}%`;
    };
    return { low: calc(0.5), default: calc(1.0), high: calc(2.0) };
  }

  if (type === "flat_bonus" || type === "flat_penalty") {
    const num = Number(value);
    const sign = type === "flat_bonus" ? 1 : -1;
    const calc = (weight: number) => {
      const delta = sign * num * weight;
      const formatted = delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);
      return `${formatted} pts`;
    };
    return { low: calc(0.5), default: calc(1.0), high: calc(2.0) };
  }

  return null;
}

export function RuleItem({ rule, onChange }: RuleItemProps) {
  return (
    <div className="flex items-start justify-between gap-2 py-1">
      <div className="flex items-start gap-2 flex-1 min-w-0">
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => onChange({ ...rule, enabled: v })}
        />
        <span className="text-sm break-words leading-snug">{rule.name}</span>
        {rule.description && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                  aria-label={`About ${rule.name}`}
                >
                  <Info className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs space-y-2">
                <p>{rule.description}</p>
                {(() => {
                  const impact = computeImpact(rule);
                  if (!impact) return null;
                  return (
                    <div className="font-mono text-[10px] text-muted-foreground border-t border-border pt-1.5">
                      Impact: low {impact.low} · default {impact.default} · high {impact.high}
                    </div>
                  );
                })()}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
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
