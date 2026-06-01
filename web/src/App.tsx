import { useEffect, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfilePicker } from "@/components/ProfilePicker";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
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
  const { user, profiles, setProfiles, refresh } = useAuth();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [rules, setRules] = useState<Rule[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [manageOpen, setManageOpen] = useState(false);
  const [linkedOpen, setLinkedOpen] = useState(false);
  const [linkingError, setLinkingError] = useState<string | null>(null);
  // Per-profile undo history. Each entry is a snapshot of a moment when state
  // was committed to the server. Tip (last entry) is the current server state.
  // Undo pops the tip and re-PATCHes the prior tip, so undo also persists.
  type Snapshot = {
    settings_json: Record<string, unknown>;
    rules_json: Array<Record<string, unknown>>;
  };
  const HISTORY_CAP = 10;
  const [history, setHistory] = useState<Record<string, Snapshot[]>>({});
  const lastSavedSnapshot: Snapshot | null = activeProfileId
    ? history[activeProfileId]?.at(-1) ?? null
    : null;
  const canUndo = activeProfileId
    ? (history[activeProfileId]?.length ?? 0) >= 2
    : false;

  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

  // Seed canonical rules list once.
  useEffect(() => {
    if (fetchedRules && !seeded) {
      setRules(fetchedRules);
      setSeeded(true);
    }
  }, [fetchedRules, seeded]);

  // On first mount, surface OAuth linking failures the backend signalled via query param.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("linking_error");
    let message: string | null = null;
    if (code === "already_linked_elsewhere") {
      message = "This Google or Yahoo account is already linked to a different AutoTiers account.";
    } else if (code === "session_lost") {
      message = "Your sign-in session was lost during the redirect. Please sign in again, then try linking the account.";
    }
    if (message !== null) {
      setLinkingError(message);
      setLinkedOpen(true);
      params.delete("linking_error");
      const rest = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (rest ? `?${rest}` : ""));
    }
  }, []);

  // On user change, set activeProfileId from the user's last-active.
  useEffect(() => {
    setActiveProfileId(user?.last_active_profile_id ?? null);
  }, [user]);

  // When activeProfileId changes, hydrate settings + rules from that profile.
  // Also seed undo history with the loaded snapshot — but only on the first
  // hydration for the profile, so existing in-memory history survives
  // profile-switch round-trips.
  useEffect(() => {
    if (!activeProfileId) return;
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
    setHistory((prev) => {
      if ((prev[activeProfileId]?.length ?? 0) > 0) return prev;
      return {
        ...prev,
        [activeProfileId]: [{
          settings_json: active.settings_json as Record<string, unknown>,
          rules_json: active.rules_json as unknown as Array<Record<string, unknown>>,
        }],
      };
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
      // Bail when the payload matches what's already saved. The autosave
      // effect fires whenever `payload` changes — including the change
      // triggered by profile hydration itself — and without this guard
      // we'd issue a wasted PATCH echoing back the just-loaded data on
      // every page load and profile switch.
      if (lastSavedSnapshot && JSON.stringify(payload) === JSON.stringify(lastSavedSnapshot)) {
        return;
      }
      const updated = await updateProfile(id, payload);
      // Append the new save point to history. Cap at HISTORY_CAP so memory
      // doesn't grow unbounded over long sessions.
      setHistory((prev) => {
        const current = prev[id] ?? [];
        const next = [...current, payload];
        if (next.length > HISTORY_CAP) next.shift();
        return { ...prev, [id]: next };
      });
      // Keep AuthContext's profiles array in sync with what's on the server.
      // Without this, switching profiles re-hydrates from the original
      // /me snapshot — so the edits the user just made get clobbered when
      // they switch away and back.
      setProfiles(profiles.map((p) => (p.id === id ? updated : p)));
    },
  });

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

  const handleUndo = useCallback(async () => {
    if (!activeProfileId || !fetchedRules) return;
    const current = history[activeProfileId];
    if (!current || current.length < 2) return;
    // Drop the current tip; the entry before it becomes the new tip.
    const trimmed = current.slice(0, -1);
    const newTip = trimmed[trimmed.length - 1];

    // Apply to local state immediately so the UI updates without waiting
    // for the server round-trip.
    setSettings(newTip.settings_json as unknown as SettingsState);
    const overrides = new Map(
      (newTip.rules_json as Array<{ name: string; enabled: boolean; weight: number }>).map((r) => [r.name, r]),
    );
    setRules(fetchedRules.map((r) => {
      const o = overrides.get(r.name);
      return o ? { ...r, enabled: o.enabled, weight: o.weight } : r;
    }));

    // Drop the popped entry from history. The autosave guard ("bail if payload
    // matches tip") now blocks the debounced save from firing redundantly —
    // but the server still has the old tip, so we PATCH explicitly here.
    setHistory((prev) => ({ ...prev, [activeProfileId]: trimmed }));
    const updated = await updateProfile(activeProfileId, newTip);
    setProfiles(profiles.map((p) => (p.id === activeProfileId ? updated : p)));
  }, [activeProfileId, fetchedRules, history, profiles, setProfiles]);

  const buildRequest = (): GenerateRequest => {
    const active = profiles.find((p) => p.id === activeProfileId);
    const linked = active?.linked_league ?? null;
    return {
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
      keepers: linked?.keepers_json?.map((k) => k.player_name) ?? undefined,
      league_adp: linked?.adp_json ?? undefined,
    };
  };

  const canGenerate = weightsAreValid(settings.weights) && rules.length > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={() => generate.mutate(buildRequest())}
        currentState={{ settings, rules }}
        onOpenLinkedAccounts={user ? () => { setLinkingError(null); setLinkedOpen(true); } : undefined}
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
            {canUndo && (
              <Button size="sm" variant="ghost" onClick={handleUndo}>
                Undo
              </Button>
            )}
          </div>
        ) : null}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden">
        <SettingsPanel
          value={settings}
          onChange={setSettings}
          linkedLeague={
            (() => {
              const active = profiles.find((p) => p.id === activeProfileId);
              const ll = active?.linked_league;
              // Only show the auto-detected chip when an actual league is selected.
              return ll && ll.league_metadata_json
                ? { provider: ll.provider, leagueName: ll.league_metadata_json.name }
                : null;
            })()
          }
          profileId={activeProfileId}
          onRefreshLink={refresh}
        />
        <RulesPanel rules={rules} onChange={setRules} />
        <TiersPanel
          result={generate.data ?? null}
          isPending={generate.isPending}
          onDownloadCsv={() => downloadCsv(buildRequest())}
          keepers={
            profiles.find((p) => p.id === activeProfileId)?.linked_league?.keepers_json ?? undefined
          }
        />
      </main>
      <ManageProfilesDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
        profiles={profiles}
        onRename={handleRenameProfile}
        onDelete={handleDeleteProfile}
      />
      {user && (
        <LinkedAccountsDialog
          open={linkedOpen}
          onOpenChange={setLinkedOpen}
          user={user}
          onRefresh={refresh}
          initialError={linkingError}
          activeProfile={profiles.find((p) => p.id === activeProfileId) ?? null}
        />
      )}
    </div>
  );
}
