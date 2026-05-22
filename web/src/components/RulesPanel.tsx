import { useMemo } from "react";
import { RuleCategory } from "./RuleCategory";
import { CustomRulesEditor } from "./CustomRulesEditor";
import type { Rule } from "@/api/types";

interface RulesPanelProps {
  rules: Rule[];
  onChange: (next: Rule[]) => void;
}

export function RulesPanel({ rules, onChange }: RulesPanelProps) {
  const grouped = useMemo(() => {
    const m = new Map<string, Rule[]>();
    for (const r of rules) {
      const cat = r.category || (r.is_builtin ? "Other" : "Custom");
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(r);
    }
    return [...m.entries()];
  }, [rules]);

  const updateRule = (updated: Rule) =>
    onChange(rules.map((r) => (r.name === updated.name ? updated : r)));

  const addCustomRule = (rule: Rule) => onChange([...rules, rule]);

  const removeCustomRule = (name: string) =>
    onChange(rules.filter((r) => r.name !== name));

  if (rules.length === 0) {
    return <aside className="p-6 border-r bg-card min-h-0 overflow-y-auto"><span className="text-sm text-muted-foreground">Loading rules…</span></aside>;
  }

  return (
    <aside className="space-y-3 border-r bg-card p-6 overflow-y-auto min-h-0">
      <h2 className="text-lg font-semibold">Rules</h2>
      {grouped.map(([cat, rs]) => (
        <RuleCategory key={cat} name={cat} rules={rs} onChangeRule={updateRule} />
      ))}
      <CustomRulesEditor
        existingNames={new Set(rules.map((r) => r.name))}
        onAdd={addCustomRule}
        onRemove={removeCustomRule}
        customRules={rules.filter((r) => !r.is_builtin)}
      />
    </aside>
  );
}
