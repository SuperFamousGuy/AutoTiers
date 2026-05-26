import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { RuleItem } from "./RuleItem";
import type { Rule } from "@/api/types";

interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  onChangeRule: (next: Rule) => void;
}

export function RuleCategory({ name, rules, onChangeRule }: RuleCategoryProps) {
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
        {rules.map((r) => (
          <RuleItem key={r.name} rule={r} onChange={onChangeRule} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
