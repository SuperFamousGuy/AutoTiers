import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { RuleItem } from "./RuleItem";
import type { Rule } from "@/api/types";

interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  onChangeRule: (next: Rule) => void;
}

export function RuleCategory({ name, rules, onChangeRule }: RuleCategoryProps) {
  return (
    <Collapsible defaultOpen className="border rounded-md">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium hover:bg-muted">
        <span>{name}</span>
        <ChevronDown className="h-4 w-4" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-2 space-y-1">
        {rules.map((r) => (
          <RuleItem key={r.name} rule={r} onChange={onChangeRule} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
