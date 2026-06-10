import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { RuleItem } from "./RuleItem";
import type { Rule, PositionRuleOverride } from "@/api/types";

interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  overrides: Record<string, PositionRuleOverride>;  // keyed by rule name
  onChangeRule: (next: PositionRuleOverride) => void;
}

export function RuleCategory({ name, rules, overrides, onChangeRule }: RuleCategoryProps) {
  const [open, setOpen] = useState(true);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="border rounded-md overflow-hidden">
      <CollapsibleTrigger className="flex w-full items-center justify-between bg-muted/60 px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted border-b">
        <span>{name}</span>
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 py-2 space-y-1 divide-y divide-border/50">
        {rules.map((r) => {
          // Build the override for this rule from the overrides map, or fall
          // back to the canonical rule's built-in enabled/weight values when no
          // per-position override has been saved yet.
          const override: PositionRuleOverride = overrides[r.name] ?? {
            name: r.name,
            enabled: r.enabled,
            weight: r.weight,
          };
          return (
            <RuleItem
              key={r.name}
              rule={r}
              override={override}
              onChange={onChangeRule}
            />
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
}
