import { useMemo } from "react";
import { RuleCategory } from "./RuleCategory";
import type { Rule } from "@/api/types";

interface RulesPanelProps {
  rules: Rule[];
  onChange: (next: Rule[]) => void;
}

export function RulesPanel({ rules, onChange }: RulesPanelProps) {
  const visibleRules = useMemo(
    () => rules.filter((r) => r.effect.type !== "flag"),
    [rules],
  );

  const grouped = useMemo(() => {
    const m = new Map<string, Rule[]>();
    for (const r of visibleRules) {
      const cat = r.category || "Other";
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(r);
    }
    return [...m.entries()];
  }, [visibleRules]);

  const updateRule = (updated: Rule) =>
    onChange(rules.map((r) => (r.name === updated.name ? updated : r)));

  if (rules.length === 0) {
    return <aside className="p-6 border-r bg-card min-h-0 overflow-y-auto"><span className="text-sm text-muted-foreground">Loading rules…</span></aside>;
  }

  return (
    <aside className="space-y-3 border-r bg-card p-6 overflow-y-auto min-h-0">
      <h2 className="text-lg font-semibold">Rules</h2>
      {grouped.map(([cat, rs]) => (
        <RuleCategory key={cat} name={cat} rules={rs} onChangeRule={updateRule} />
      ))}
    </aside>
  );
}
