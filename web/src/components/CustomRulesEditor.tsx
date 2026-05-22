import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import type { Rule, RuleCondition, RuleEffect } from "@/api/types";

interface CustomRulesEditorProps {
  existingNames: Set<string>;
  customRules: Rule[];
  onAdd: (rule: Rule) => void;
  onRemove: (name: string) => void;
}

interface ParseResult {
  ok: boolean;
  rule?: Rule;
  error?: string;
}

function parseRule(input: string, existingNames: Set<string>): ParseResult {
  if (!input.trim()) return { ok: false, error: "" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch (e) {
    return { ok: false, error: `Invalid JSON: ${(e as Error).message}` };
  }
  if (!parsed || typeof parsed !== "object") return { ok: false, error: "Must be a JSON object" };
  const p = parsed as Partial<Rule>;
  if (typeof p.name !== "string" || !p.name) return { ok: false, error: "Missing 'name' (string)" };
  if (existingNames.has(p.name)) return { ok: false, error: `Rule '${p.name}' already exists` };
  if (!Array.isArray(p.conditions) || p.conditions.length === 0) {
    return { ok: false, error: "Missing 'conditions' (non-empty array)" };
  }
  if (!p.effect || typeof p.effect !== "object") return { ok: false, error: "Missing 'effect' (object)" };
  return {
    ok: true,
    rule: {
      name: p.name,
      conditions: p.conditions as RuleCondition[],
      effect: p.effect as RuleEffect,
      enabled: true,
      weight: 1.0,
      is_builtin: false,
      category: "Custom",
    },
  };
}

export function CustomRulesEditor({
  existingNames,
  customRules,
  onAdd,
  onRemove,
}: CustomRulesEditorProps) {
  const [input, setInput] = useState("");
  const [result, setResult] = useState<ParseResult>({ ok: false });

  useEffect(() => {
    const t = setTimeout(() => setResult(parseRule(input, existingNames)), 300);
    return () => clearTimeout(t);
  }, [input, existingNames]);

  return (
    <div className="border rounded-md p-3 space-y-2">
      <h3 className="text-sm font-medium">Custom rules</h3>
      {customRules.length > 0 && (
        <ul className="space-y-1">
          {customRules.map((r) => (
            <li key={r.name} className="flex items-center justify-between text-sm">
              <span className="truncate">{r.name}</span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`remove ${r.name}`}
                onClick={() => onRemove(r.name)}
              >
                <X className="h-3 w-3" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <textarea
        className="w-full h-32 rounded-md border border-input bg-background p-2 text-xs font-mono"
        placeholder='{"name": "My Rule", "conditions": [...], "effect": {...}}'
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      {input && (
        result.ok ? (
          <p className="text-xs text-green-600">✓ Valid</p>
        ) : result.error ? (
          <p className="text-xs text-red-600">{result.error}</p>
        ) : null
      )}
      <Button
        size="sm"
        disabled={!result.ok}
        onClick={() => {
          if (result.rule) {
            onAdd(result.rule);
            setInput("");
            setResult({ ok: false });
          }
        }}
      >
        Add rule
      </Button>
    </div>
  );
}
