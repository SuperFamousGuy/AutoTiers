import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { Rule } from "@/api/types";

interface RuleItemProps {
  rule: Rule;
  onChange: (next: Rule) => void;
}

type ImpactInfo = {
  unit: string;
  sign: "+" | "−";
  magnitudeFor: (weight: number) => number;
  weightFor: (magnitude: number) => number;
};

function getImpactInfo(rule: Rule): ImpactInfo | null {
  const round4 = (n: number) => Math.round(n * 10000) / 10000;
  const { type, value } = rule.effect;
  if (type === "multiplier") {
    const distance = Number(value) - 1.0;
    if (distance === 0) return null;
    const absDist = Math.abs(distance);
    return {
      unit: "%",
      sign: distance > 0 ? "+" : "−",
      magnitudeFor: (w) => absDist * w * 100,
      weightFor: (m) => round4(m / 100 / absDist),
    };
  }
  if (type === "flat_bonus" || type === "flat_penalty") {
    const v = Math.abs(Number(value));
    if (v === 0) return null;
    return {
      unit: " pts",
      sign: type === "flat_bonus" ? "+" : "−",
      magnitudeFor: (w) => v * w,
      weightFor: (m) => round4(m / v),
    };
  }
  return null;
}

function formatMagnitude(m: number): string {
  const fixed = m.toFixed(1);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed;
}

export function RuleItem({ rule, onChange }: RuleItemProps) {
  const [expanded, setExpanded] = useState(false);
  const impact = getImpactInfo(rule);
  const [inputValue, setInputValue] = useState<string>(
    impact ? formatMagnitude(impact.magnitudeFor(rule.weight)) : "",
  );

  useEffect(() => {
    if (impact) {
      setInputValue(formatMagnitude(impact.magnitudeFor(rule.weight)));
    }
    // Re-sync only when external rule state changes — not on every render.
  }, [rule.weight, rule.effect.type, rule.effect.value]);

  function commit(magnitudeStr: string) {
    if (!impact) return;
    const m = parseFloat(magnitudeStr);
    if (Number.isNaN(m) || m < 0) {
      setInputValue(formatMagnitude(impact.magnitudeFor(rule.weight)));
      return;
    }
    onChange({ ...rule, weight: impact.weightFor(m) });
  }

  function applySuggestion(weight: number) {
    onChange({ ...rule, weight });
  }

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <div className="flex items-center gap-2 py-1">
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => onChange({ ...rule, enabled: v })}
        />
        <span className="text-sm flex-1 break-words leading-snug">{rule.name}</span>
        <CollapsibleTrigger
          className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0 p-1 -m-1"
          aria-label={`Toggle details for ${rule.name}`}
        >
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", expanded && "rotate-180")}
          />
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="pb-2 pl-9 pr-2 text-xs space-y-2">
        {rule.description && (
          <p className="text-muted-foreground leading-snug">{rule.description}</p>
        )}
        {impact && (
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => applySuggestion(0.5)}
              disabled={!rule.enabled}
              className="rounded border bg-background px-2 py-0.5 text-foreground shadow-sm hover:bg-muted hover:border-foreground/30 active:bg-muted/80 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-background disabled:hover:border-input font-mono transition-colors"
            >
              Low: {impact.sign}{formatMagnitude(impact.magnitudeFor(0.5))}{impact.unit}
            </button>
            <div className="flex items-center gap-0.5 font-mono">
              <span className="text-muted-foreground">{impact.sign}</span>
              <input
                type="number"
                step="any"
                min="0"
                value={inputValue}
                disabled={!rule.enabled}
                onChange={(e) => setInputValue(e.target.value)}
                onBlur={() => commit(inputValue)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                }}
                className="w-14 px-1 py-0.5 border rounded text-center bg-background disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label={`${rule.name} adjustment magnitude`}
              />
              <span className="text-muted-foreground">{impact.unit}</span>
            </div>
            <button
              type="button"
              onClick={() => applySuggestion(2.0)}
              disabled={!rule.enabled}
              className="rounded border bg-background px-2 py-0.5 text-foreground shadow-sm hover:bg-muted hover:border-foreground/30 active:bg-muted/80 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-background disabled:hover:border-input font-mono transition-colors"
            >
              High: {impact.sign}{formatMagnitude(impact.magnitudeFor(2.0))}{impact.unit}
            </button>
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
