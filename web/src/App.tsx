import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { useRules, useGenerateMutation, downloadCsv } from "@/api/hooks";
import { weightsAreValid } from "@/lib/weights";
import type { Rule, GenerateRequest } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "ppr",
  league_type: "standard",
  league_size: 12,
  draft_rounds: 15,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weights: { prior: 40, espn: 30, consensus: 30 },
};

export default function App() {
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [rules, setRules] = useState<Rule[]>([]);
  const [seeded, setSeeded] = useState(false);
  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

  // Seed local rules state once the backend response arrives.
  useEffect(() => {
    if (fetchedRules && !seeded) {
      setRules(fetchedRules);
      setSeeded(true);
    }
  }, [fetchedRules, seeded]);

  const buildRequest = (): GenerateRequest => ({
    scoring_format: settings.scoring_format,
    league_type: settings.league_type,
    league_size: settings.league_size,
    qb_td_points: settings.qb_td_points,
    bonus_100yd_rushing: settings.bonus_100yd_rushing,
    bonus_100yd_receiving: settings.bonus_100yd_receiving,
    bonus_first_downs: settings.bonus_first_downs,
    weight_prior_year: settings.weights.prior / 100,
    weight_espn: settings.weights.espn / 100,
    weight_consensus: settings.weights.consensus / 100,
    draft_rounds: settings.draft_rounds,
    rules,
  });

  const canGenerate = weightsAreValid(settings.weights) && rules.length > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={() => generate.mutate(buildRequest())}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] overflow-hidden">
        <SettingsPanel value={settings} onChange={setSettings} />
        <RulesPanel rules={rules} onChange={setRules} />
        <TiersPanel
          result={generate.data ?? null}
          isPending={generate.isPending}
          onDownloadCsv={() => downloadCsv(buildRequest())}
        />
      </main>
    </div>
  );
}
