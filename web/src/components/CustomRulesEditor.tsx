import type { Rule } from "@/api/types";

interface CustomRulesEditorProps {
  existingNames: Set<string>;
  customRules: Rule[];
  onAdd: (rule: Rule) => void;
  onRemove: (name: string) => void;
}

// Stub — full implementation in Task 12.
export function CustomRulesEditor(_props: CustomRulesEditorProps) {
  return null;
}
