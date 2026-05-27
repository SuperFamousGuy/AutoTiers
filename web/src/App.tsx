import { useEffect, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfilePicker } from "@/components/ProfilePicker";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import { Button } from "@/components/ui/button";
import { useRules, useGenerateMutation, downloadCsv } from "@/api/hooks";
import { useAuth } from "@/contexts/AuthContext";
import { createProfile, updateProfile, deleteProfile, activateProfile } from "@/api/profiles";
import { useAutoSave } from "@/hooks/useAutoSave";
import { weightsAreValid } from "@/lib/weights";
import type { Rule, GenerateRequest } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "standard",
  league_size: 12,
  draft_rounds: 15,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weights: { prior: 30, consensus: 70 },
};

export default function App() {
  const { user, profiles, setProfiles } = useAuth();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [rules, setRules] = useState<Rule[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [manageOpen, setManageOpen] = useState(false);
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState<{
    settings_json: Record<string, unknown>;
    rules_json: Array<Record<string, unknown>>;
  } | null>(null);

  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

  // Seed canonical rules list once.
  useEffect(() => {
    if (fetchedRules && !seeded) {
      setRules(fetchedRules);
      setSeeded(true);
    }
  }, [fetchedRules, seeded]);

  // On user change, set activeProfileId from the user's last-active.
  useEffect(() => {
    setActiveProfileId(user?.last_active_profile_id ?? null);
  }, [user]);

  // When activeProfileId changes, hydrate settings + rules + snapshot from that profile.
  useEffect(() => {
    if (!activeProfileId) {
      setLastSavedSnapshot(null);
      return;
    }
    const active = profiles.find((p) => p.id === activeProfileId);
    if (!active) return;

    setSettings(active.settings_json as unknown as SettingsState);
    if (fetchedRules) {
      const overrides = new Map(active.rules_json.map((r) => [r.name, r]));
      setRules(fetchedRules.map((r) => {
        const o = overrides.get(r.name);
        return o ? { ...r, enabled: o.enabled, weight: o.weight } : r;
      }));
    }
    setLastSavedSnapshot({
      settings_json: active.settings_json as Record<string, unknown>,
      rules_json: active.rules_json as unknown as Array<Record<string, unknown>>,
    });
  }, [activeProfileId, profiles, fetchedRules]);

  const autosavePayload = useMemo(() => ({
    settings_json: settings as unknown as Record<string, unknown>,
    rules_json: rules.map((r) => ({ name: r.name, enabled: r.enabled, weight: r.weight })) as unknown as Array<Record<string, unknown>>,
  }), [settings, rules]);

  useAutoSave({
    activeId: user ? activeProfileId : null,
    payload: autosavePayload,
    save: async (id, payload) => {
      await updateProfile(id, payload);
      setLastSavedSnapshot(payload);
    },
  });

  const isDirty = useMemo(() => {
    if (!lastSavedSnapshot) return false;
    return JSON.stringify(autosavePayload) !== JSON.stringify(lastSavedSnapshot);
  }, [autosavePayload, lastSavedSnapshot]);

  const handleSelectProfile = useCallback(async (id: string) => {
    setActiveProfileId(id);
    await activateProfile(id);
  }, []);

  const handleNewProfile = useCallback(async () => {
    const created = await createProfile({
      name: `Profile ${profiles.length + 1}`,
      settings_json: settings as unknown as Record<string, unknown>,
      rules_json: rules.map((r) => ({ name: r.name, enabled: r.enabled, weight: r.weight })),
    });
    setProfiles([...profiles, created]);
    setActiveProfileId(created.id);
    await activateProfile(created.id);
  }, [profiles, settings, rules, setProfiles]);

  const handleRenameProfile = useCallback(async (id: string, name: string) => {
    const updated = await updateProfile(id, { name });
    setProfiles(profiles.map((p) => (p.id === id ? updated : p)));
  }, [profiles, setProfiles]);

  const handleDeleteProfile = useCallback(async (id: string) => {
    await deleteProfile(id);
    setProfiles(profiles.filter((p) => p.id !== id));
    if (activeProfileId === id) setActiveProfileId(null);
  }, [profiles, activeProfileId, setProfiles]);

  const handleResetToSaved = useCallback(() => {
    if (!lastSavedSnapshot || !fetchedRules) return;
    setSettings(lastSavedSnapshot.settings_json as unknown as SettingsState);
    const overrides = new Map(
      (lastSavedSnapshot.rules_json as Array<{ name: string; enabled: boolean; weight: number }>).map((r) => [r.name, r]),
    );
    setRules(fetchedRules.map((r) => {
      const o = overrides.get(r.name);
      return o ? { ...r, enabled: o.enabled, weight: o.weight } : r;
    }));
  }, [lastSavedSnapshot, fetchedRules]);

  const buildRequest = (): GenerateRequest => ({
    scoring_format: settings.scoring_format,
    league_type: "standard",
    league_size: settings.league_size,
    qb_td_points: settings.qb_td_points,
    bonus_100yd_rushing: settings.bonus_100yd_rushing,
    bonus_100yd_receiving: settings.bonus_100yd_receiving,
    bonus_first_downs: settings.bonus_first_downs,
    weight_prior_year: settings.weights.prior / 100,
    weight_espn: 0,
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
        currentState={{ settings, rules }}
        profilePicker={user ? (
          <div className="flex items-center gap-2">
            <ProfilePicker
              profiles={profiles}
              activeId={activeProfileId}
              onSelect={handleSelectProfile}
              onNew={handleNewProfile}
              onManage={() => setManageOpen(true)}
              canCreate={profiles.length < 5}
            />
            {isDirty && (
              <Button size="sm" variant="ghost" onClick={handleResetToSaved}>
                Reset to saved
              </Button>
            )}
          </div>
        ) : null}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden">
        <SettingsPanel value={settings} onChange={setSettings} />
        <RulesPanel rules={rules} onChange={setRules} />
        <TiersPanel
          result={generate.data ?? null}
          isPending={generate.isPending}
          onDownloadCsv={() => downloadCsv(buildRequest())}
        />
      </main>
      <ManageProfilesDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
        profiles={profiles}
        onRename={handleRenameProfile}
        onDelete={handleDeleteProfile}
      />
    </div>
  );
}
