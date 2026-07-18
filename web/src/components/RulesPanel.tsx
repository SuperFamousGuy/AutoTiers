import { useMemo, useState } from "react";
import { RuleCategory } from "./RuleCategory";
import type { Rule, PositionRulesState, PositionRuleOverride } from "@/api/types";
import { POSITIONS, POSITION_RULES_MAP, type Position } from "@/lib/positionRulesMap";
import { cn } from "@/lib/utils";

interface RulesPanelProps {
  canonicalRules: Rule[];
  positionRules: PositionRulesState;
  onChange: (next: PositionRulesState) => void;
  /** True when the GET /api/rules query has failed (after retries exhausted). */
  isError?: boolean;
  /** Retries the rules fetch — wired to react-query's refetch. */
  onRetry?: () => void;
}

/**
 * The disabled position-tab strip shared by the loading and error states, so
 * both render the same chrome and only the status line below differs.
 */
function DisabledTabStrip() {
  return (
    <div role="tablist" aria-label="Position" className="flex gap-1 mb-4">
      {POSITIONS.map((pos) => (
        <button
          key={pos}
          role="tab"
          aria-selected={false}
          id={`tab-${pos}`}
          disabled
          className="rounded px-2.5 py-1 text-xs font-semibold font-mono bg-muted text-muted-foreground opacity-50 cursor-not-allowed"
        >
          {pos}
        </button>
      ))}
    </div>
  );
}

export function RulesPanel({
  canonicalRules,
  positionRules,
  onChange,
  isError = false,
  onRetry,
}: RulesPanelProps) {
  const [activePosition, setActivePosition] = useState<Position>("RB");

  // Three distinct states, checked in precedence order below:
  //  - ERROR  : the fetch failed AND there are no rules to fall back on. A hard
  //             failure no longer masquerades as an eternal "Loading rules…"
  //             spinner. If a prior fetch already seeded rules, react-query keeps
  //             that data on a failed refetch — we keep showing those usable rules
  //             rather than blanking to an error.
  //  - LOADING: no rules yet AND no error → still in flight.
  //  - LOADED : rules present.
  const hasRules = canonicalRules.length > 0;
  const showError = isError && !hasRules;
  const isLoading = !hasRules && !isError;

  // Filter canonical rules to those in the active position's mapping, in mapping order.
  const positionRuleNames = POSITION_RULES_MAP[activePosition];
  const rulesForPosition = useMemo(() => {
    const byName = new Map(canonicalRules.map((r) => [r.name, r]));
    return positionRuleNames
      .map((name) => byName.get(name))
      .filter((r): r is Rule => r !== undefined && r.effect.type !== "flag");
  }, [canonicalRules, positionRuleNames]);

  // Group by category.
  const grouped = useMemo(() => {
    const m = new Map<string, Rule[]>();
    for (const r of rulesForPosition) {
      const cat = r.category || "Other";
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(r);
    }
    return [...m.entries()];
  }, [rulesForPosition]);

  // Build an overrides lookup for the active position, keyed by rule name.
  const overridesForPosition = useMemo<Record<string, PositionRuleOverride>>(() => {
    const overrides = positionRules[activePosition] ?? [];
    return Object.fromEntries(overrides.map((o) => [o.name, o]));
  }, [positionRules, activePosition]);

  // Which position tabs carry at least one *customized* override — i.e. an
  // override whose enabled/weight differs from the canonical rule's default.
  // Autosave can persist a no-op override that matches the default in both
  // fields; that does not count as customized, so the tab stays unmarked.
  const customizedPositions = useMemo<Set<Position>>(() => {
    const byName = new Map(canonicalRules.map((r) => [r.name, r]));
    const marked = new Set<Position>();
    for (const pos of POSITIONS) {
      const overrides = positionRules[pos] ?? [];
      const hasCustom = overrides.some((o) => {
        const canonical = byName.get(o.name);
        // No canonical to compare against → can't call it customized.
        if (!canonical) return false;
        return o.enabled !== canonical.enabled || o.weight !== canonical.weight;
      });
      if (hasCustom) marked.add(pos);
    }
    return marked;
  }, [canonicalRules, positionRules]);

  function updateRule(positionName: string, updated: PositionRuleOverride) {
    const current = positionRules[positionName] ?? [];
    const existsIdx = current.findIndex((r) => r.name === updated.name);
    let next: PositionRuleOverride[];
    if (existsIdx >= 0) {
      next = current.map((r, i) => (i === existsIdx ? updated : r));
    } else {
      next = [...current, updated];
    }
    onChange({ ...positionRules, [positionName]: next });
  }

  if (showError) {
    return (
      <aside className="p-6 border-r bg-card min-h-0 overflow-y-auto" role="alert">
        <DisabledTabStrip />
        <p className="text-sm text-destructive font-medium mb-3">
          Couldn't load rules.
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Retry
          </button>
        )}
      </aside>
    );
  }

  if (isLoading) {
    return (
      <aside className="p-6 border-r bg-card min-h-0 overflow-y-auto">
        <DisabledTabStrip />
        <span className="text-sm text-muted-foreground">Loading rules…</span>
      </aside>
    );
  }

  return (
    <aside className="space-y-3 border-r bg-card p-6 overflow-y-auto min-h-0">
      <h2 className="text-lg font-semibold">Rules</h2>

      {/* Position tab strip */}
      <div role="tablist" aria-label="Position" className="flex gap-1 flex-nowrap overflow-x-auto pb-1">
        {POSITIONS.map((pos) => {
          const isActive = pos === activePosition;
          const isCustomized = customizedPositions.has(pos);
          return (
            <button
              key={pos}
              role="tab"
              aria-selected={isActive}
              aria-controls="rules-tabpanel"
              // The dot is aria-hidden, so a customized tab would otherwise
              // announce identically to an untouched one. Fold the state into
              // the accessible name (mirrors LinkedAccountsDialog's #665 fix).
              aria-label={isCustomized ? `${pos}, customized` : pos}
              id={`tab-${pos}`}
              onClick={() => setActivePosition(pos)}
              onKeyDown={(e) => {
                const posIdx = POSITIONS.indexOf(pos);
                if (e.key === "ArrowRight") {
                  const next = POSITIONS[(posIdx + 1) % POSITIONS.length];
                  setActivePosition(next);
                  document.getElementById(`tab-${next}`)?.focus();
                } else if (e.key === "ArrowLeft") {
                  const prev = POSITIONS[(posIdx - 1 + POSITIONS.length) % POSITIONS.length];
                  setActivePosition(prev);
                  document.getElementById(`tab-${prev}`)?.focus();
                }
              }}
              className={cn(
                "inline-flex items-center rounded px-2.5 py-1 text-xs font-semibold font-mono flex-shrink-0 transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80",
              )}
            >
              {pos}
              {isCustomized && (
                <span
                  className="ml-1 h-1.5 w-1.5 rounded-full bg-green-500"
                  aria-hidden="true"
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Rule list for active position */}
      <div
        role="tabpanel"
        id="rules-tabpanel"
        aria-labelledby={`tab-${activePosition}`}
        className="space-y-3"
      >
        {grouped.map(([cat, rs]) => (
          <RuleCategory
            key={cat}
            name={cat}
            rules={rs}
            overrides={overridesForPosition}
            onChangeRule={(next) => updateRule(activePosition, next)}
          />
        ))}
      </div>
    </aside>
  );
}
