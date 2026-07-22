import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useOnboarding } from "@/hooks/useOnboarding";
import { OnboardingTour } from "@/components/OnboardingTour";
import { ONBOARDING_STEPS } from "@/lib/onboardingSteps";
import { SettingsPanel, DEFAULT_FULL_SEASON_GAMES, DEFAULT_PRIOR_YEAR_RAMP, DEFAULT_TE_PREMIUM, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfileSwitcher } from "@/components/ProfileSwitcher";
import { MobileProfileMenuItems } from "@/components/MobileProfileMenuItems";
import { ProfileManagerDialog } from "@/components/ProfileManagerDialog";
import { MobilePanelTabBar, type MobilePanel } from "@/components/MobilePanelTabBar";
import { AdSlot } from "@/components/AdSlot";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useRules, useGenerateMutation, downloadDraftXlsx, downloadDebugCsv } from "@/api/hooks";
import { useLocalProfiles } from "@/hooks/useLocalProfiles";
import { useLocalFavorites } from "@/hooks/useLocalFavorites";
import { useAutoSave } from "@/hooks/useAutoSave";
import { describeGenerateError } from "@/lib/errors";
import { generateDisabledReason } from "@/lib/generateGuard";
import { buildResolvedTierNames, resolveTierLabelOverrides } from "@/lib/tiers";
import type { Rule, GenerateRequest, PositionRulesState } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "half_ppr",
  qb_starters: 1,
  league_size: 12,
  draft_rounds: 15,
  tier_count: 12,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  te_premium_bonus: DEFAULT_TE_PREMIUM,
  weights: { prior: 30, consensus: 70 },
  full_season_games: DEFAULT_FULL_SEASON_GAMES,
  prior_year_ramp: DEFAULT_PRIOR_YEAR_RAMP,
};

/** The next "Profile N" name that doesn't collide with an existing one —
 * `useLocalProfiles.create` throws on an exact duplicate name. */
function nextProfileName(existing: { name: string }[]): string {
  const names = new Set(existing.map((p) => p.name));
  let n = existing.length + 1;
  while (names.has(`Profile ${n}`)) n++;
  return `Profile ${n}`;
}

export default function App() {
  const [isDark, toggleDark] = useDarkMode();
  const {
    active: tourActive,
    stepIndex: tourStep,
    totalSteps: tourTotal,
    start: startOnboarding,
    next: tourNext,
    back: tourBack,
    goTo: tourGoTo,
    skip: tourSkip,
  } = useOnboarding(ONBOARDING_STEPS.length);
  const { profiles, active: activeProfile, create, update, rename, remove, activate } = useLocalProfiles();
  const { isFavoritePlayer, isFavoriteTeam } = useLocalFavorites();
  const { toast } = useToast();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  // Dev-only debug export: surfaces the full debug CSV button when the app URL
  // carries ?debug=1. Read once on mount; not stripped by the query-param cleanup.
  const [debugMode] = useState(
    () => new URLSearchParams(window.location.search).get("debug") === "1",
  );
  // Canonical rule definitions from GET /rules (used to seed defaults and display).
  // Never mutated directly by the user — the user's changes go into positionRules.
  const [canonicalRules, setCanonicalRules] = useState<Rule[]>([]);
  // Per-position override state — what gets saved and sent to generate.
  const [positionRules, setPositionRules] = useState<PositionRulesState>({});
  const [seeded, setSeeded] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  // Mobile panel state: "settings" when no result exists yet, "tiers" once a result exists.
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("settings");
  // Guard: auto-switch to Tiers only on the FIRST generate result after app load
  // (or after a profile switch). Reset to false on profile change so the next
  // generate result after switching profiles auto-switches again.
  const hasAutoSwitchedToTiers = useRef(false);

  const activeProfileId = activeProfile?.id ?? null;

  // First-run only: with no accounts, a brand-new visitor has zero local
  // profiles. Auto-create one so Settings/Rules edits have somewhere to
  // autosave into immediately, rather than silently going nowhere until the
  // user notices and clicks "+ New Profile" themselves.
  const didAutoCreate = useRef(false);
  useEffect(() => {
    if (didAutoCreate.current) return;
    didAutoCreate.current = true;
    if (profiles.length === 0) {
      create("My Settings", DEFAULT_SETTINGS as unknown as Record<string, unknown>, {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Per-profile undo history. Each entry is a snapshot of a moment when state
  // was committed to the profile. Tip (last entry) is the current saved state.
  // Undo pops the tip and re-applies the prior tip, so undo also persists.
  type Snapshot = {
    settings_json: Record<string, unknown>;
    rules_json: Record<string, unknown>;
  };
  const HISTORY_CAP = 10;
  const [history, setHistory] = useState<Record<string, Snapshot[]>>({});
  const lastSavedSnapshot: Snapshot | null = activeProfileId
    ? history[activeProfileId]?.at(-1) ?? null
    : null;
  const canUndo = activeProfileId
    ? (history[activeProfileId]?.length ?? 0) >= 2
    : false;

  const {
    data: fetchedRules,
    isError: rulesError,
    refetch: refetchRules,
  } = useRules();
  const generate = useGenerateMutation();
  // The GenerateRequest that produced the currently-displayed tier list. Set on
  // every successful generate; diffed against the live request each render to
  // detect stale results (settings/rules edited after generating). Null before
  // the first generate and after a profile switch clears the result (#523).
  const [lastGeneratedRequest, setLastGeneratedRequest] = useState<GenerateRequest | null>(null);

  // Smart mobile default: switch to "tiers" tab on the FIRST generate result after
  // app load or profile switch. Subsequent generates leave the user's current tab
  // selection intact so manually navigating away stays respected.
  useEffect(() => {
    if (generate.data && !hasAutoSwitchedToTiers.current) {
      hasAutoSwitchedToTiers.current = true;
      setMobilePanel("tiers");
    }
  }, [generate.data]);

  // Seed canonical rules list once.
  useEffect(() => {
    if (fetchedRules && !seeded) {
      setCanonicalRules(fetchedRules);
      setSeeded(true);
    }
  }, [fetchedRules, seeded]);

  // When the active profile changes, hydrate settings + positionRules from it.
  // Also seed undo history with the loaded snapshot — but only on the first
  // hydration for the profile, so existing in-memory history survives
  // profile-switch round-trips.
  useEffect(() => {
    if (!activeProfileId) return;
    const active = profiles.find((p) => p.id === activeProfileId);
    if (!active) return;

    setSettings(active.settings as unknown as SettingsState);
    setPositionRules(active.rules as unknown as PositionRulesState);
    setHistory((prev) => {
      if ((prev[activeProfileId]?.length ?? 0) > 0) return prev;
      return {
        ...prev,
        [activeProfileId]: [{
          settings_json: active.settings as Record<string, unknown>,
          rules_json: active.rules as Record<string, unknown>,
        }],
      };
    });
  }, [activeProfileId, profiles]);

  const autosavePayload = useMemo(() => ({
    settings_json: settings as unknown as Record<string, unknown>,
    rules_json: positionRules as unknown as Record<string, unknown>,
  }), [settings, positionRules]);

  useAutoSave({
    activeId: activeProfileId,
    payload: autosavePayload,
    save: async (id, payload) => {
      // Bail when the payload matches what's already saved. The autosave
      // effect fires whenever `payload` changes — including the change
      // triggered by profile hydration itself — and without this guard
      // we'd issue a wasted write echoing back the just-loaded data on
      // every page load and profile switch.
      if (lastSavedSnapshot && JSON.stringify(payload) === JSON.stringify(lastSavedSnapshot)) {
        return;
      }
      update(id, { settings: payload.settings_json, rules: payload.rules_json });
      // Append the new save point to history. Cap at HISTORY_CAP so memory
      // doesn't grow unbounded over long sessions.
      setHistory((prev) => {
        const current = prev[id] ?? [];
        const next = [...current, payload];
        if (next.length > HISTORY_CAP) next.shift();
        return { ...prev, [id]: next };
      });
    },
  });

  const handleSelectProfile = useCallback((id: string) => {
    activate(id);
    // Return the mobile view to Settings on profile switch so the user sees
    // the newly-loaded settings, and reset the auto-switch guard so the next
    // generate result after switching will auto-navigate to Tiers again.
    setMobilePanel("settings");
    hasAutoSwitchedToTiers.current = false;
    // Clear the previous profile's generate result so the Tiers panel shows
    // its empty state rather than the prior profile's stale tiers. Pairs with
    // the guard reset above: the next generate is treated as a fresh first
    // result and re-fires the mobile auto-switch.
    generate.reset();
    // Drop the captured request so the staleness banner can't compare the new
    // profile's live settings against the previous profile's generate (#523).
    setLastGeneratedRequest(null);
  }, [activate, generate.reset]);

  const handleNewProfile = useCallback(() => {
    const name = nextProfileName(profiles);
    create(
      name,
      settings as unknown as Record<string, unknown>,
      positionRules as unknown as Record<string, unknown>,
    );
    // Match the select-profile path: return to Settings, re-arm the auto-switch
    // guard, and clear the stale generate result so the new profile starts from
    // the empty state.
    setMobilePanel("settings");
    hasAutoSwitchedToTiers.current = false;
    generate.reset();
    setLastGeneratedRequest(null);
  }, [profiles, settings, positionRules, create, generate.reset]);

  const handleRenameProfile = useCallback((id: string, name: string) => {
    rename(id, name);
  }, [rename]);

  const handleDeleteProfile = useCallback((id: string) => {
    const wasActive = activeProfileId === id;
    remove(id);
    if (wasActive) {
      // Deleting the active profile must clear the orphaned tier list
      // (computed for a now-deleted profile), return the mobile view to
      // Settings, re-arm the auto-switch guard, and drop the captured request
      // so the staleness banner has nothing to compare against. Without this
      // the Tiers panel keeps rendering stale tiers and Generate would fire
      // with a silently wrong payload (#626).
      generate.reset();
      setLastGeneratedRequest(null);
      setMobilePanel("settings");
      hasAutoSwitchedToTiers.current = false;
    }
  }, [activeProfileId, remove, generate.reset]);

  const handleUndo = useCallback(() => {
    if (!activeProfileId) return;
    const current = history[activeProfileId];
    if (!current || current.length < 2) return;
    // Drop the current tip; the entry before it becomes the new tip.
    const trimmed = current.slice(0, -1);
    const newTip = trimmed[trimmed.length - 1];

    setSettings(newTip.settings_json as unknown as SettingsState);
    setPositionRules(newTip.rules_json as unknown as PositionRulesState);
    setHistory((prev) => ({ ...prev, [activeProfileId]: trimmed }));
    update(activeProfileId, { settings: newTip.settings_json, rules: newTip.rules_json });
    // Confirm the (otherwise silent) revert so a mis-click next to the
    // ProfileSwitcher is at least visible and self-explanatory (#694).
    toast({ title: "Reverted to previous settings", variant: "success" });
  }, [activeProfileId, history, update, toast]);

  const buildRequest = (): GenerateRequest => {
    return {
      scoring_format: settings.scoring_format,
      league_type: "standard",
      league_size: settings.league_size,
      // #724: superflex/2-QB toggle. Omitted (undefined) drops from the JSON body so
      // the backend applies its single-QB default.
      qb_starters: settings.qb_starters,
      qb_td_points: settings.qb_td_points,
      bonus_100yd_rushing: settings.bonus_100yd_rushing,
      bonus_100yd_receiving: settings.bonus_100yd_receiving,
      bonus_first_downs: settings.bonus_first_downs,
      te_premium_bonus: settings.te_premium_bonus,
      weight_prior_year: settings.weights.prior / 100,
      weight_espn: 0,
      weight_consensus: settings.weights.consensus / 100,
      full_season_games: settings.full_season_games,
      prior_year_ramp: settings.prior_year_ramp,
      draft_rounds: settings.draft_rounds,
      overall_tier_count: settings.tier_count ?? settings.league_size,
      rules: positionRules,
    };
  };

  // Generate needs valid weights, loaded rules, and — when profiles exist — an
  // active profile. Deleting the active profile sets activeProfileId to null;
  // without this guard Generate would stay enabled and fire buildRequest() with
  // keepers/league_adp silently undefined (profiles.find returns undefined)
  // (#626). A user with zero profiles yet (first paint, before auto-create
  // lands) stays able to generate.
  //
  // When disabled, name the *specific* unmet precondition so the button isn't a
  // silent grey rectangle for mouse or screen-reader users (#838). The priority
  // order (profile > weights > rules) lives in `generateDisabledReason`.
  // `reason === null` is exactly the enabled state.
  const disabledReason = generateDisabledReason({
    weights: settings.weights,
    ruleCount: canonicalRules.length,
    rulesError,
    profileCount: profiles.length,
    activeProfileId,
  });
  const canGenerate = disabledReason === null;

  // The request the current settings/rules would send. Recomputed each render so
  // the staleness check below reflects edits within a single render (#523).
  const currentRequest = buildRequest();

  // Fires a generate and, on success, records the exact request that produced
  // the result — the baseline the staleness banner compares against.
  const handleGenerate = () => {
    // Recompute the request at click time (rather than reusing the render-closure
    // `currentRequest`) and record the exact payload the mutation sent via the
    // onSuccess `variables` arg, so `lastGeneratedRequest` can't drift from what
    // was actually generated even if state changed between renders (#523).
    const request = buildRequest();
    generate.mutate(request, {
      onSuccess: (_data, variables) => setLastGeneratedRequest(variables),
      // Without this, a failed generate lands in the mutation's error state and
      // stops there — the user is silently shown the pre-generate empty state.
      // Surface the failure with a toast; TiersPanel renders the in-panel alert
      // + Retry from generate.isError/error (#607).
      onError: (err) =>
        toast({
          title: "Generate failed",
          description: describeGenerateError(err),
          variant: "error",
        }),
    });
  };

  // The displayed tier list is stale when the live request no longer matches the
  // one that generated it. Requires an existing result: no banner before the
  // first generate, and none while the empty/loading states are showing (#523).
  const isStale =
    generate.data != null &&
    lastGeneratedRequest != null &&
    JSON.stringify(currentRequest) !== JSON.stringify(lastGeneratedRequest);

  // Tier labels shown/exported for the active scoring format: per-format
  // overrides win over the global tier_labels, which win over static defaults (#164).
  const resolvedTierNames = buildResolvedTierNames(
    settings.tier_count ?? settings.league_size,
    resolveTierLabelOverrides(
      settings.tier_labels,
      settings.tier_labels_by_format,
      settings.scoring_format,
    ),
  );

  return (
    <div className="flex flex-col h-screen">
      {/* Skip link — the first focusable element on the page so keyboard and
          screen-reader users can jump straight to the panels without tabbing
          through every header control (WCAG 2.4.1 Bypass Blocks, #811). Kept
          visually hidden via `sr-only` until focused, at which point
          `focus:not-sr-only` brings it on-screen. Targets the <main> region,
          which carries id="main-content" and tabIndex={-1}. The onClick handler
          moves focus onto <main> explicitly — bare fragment navigation
          (`#main-content`) doesn't reliably shift focus across browsers/AT, so
          the handler is what satisfies the "focus lands on <main>" criterion. */}
      <a
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          const main = document.getElementById("main-content");
          if (main) {
            main.focus();
            main.scrollIntoView();
          }
        }}
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-foreground focus:shadow-lg focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>
      <Header
        generateDisabled={!canGenerate}
        generateDisabledReason={disabledReason}
        generateIsPending={generate.isPending}
        onGenerate={handleGenerate}
        isDark={isDark}
        onToggleDark={toggleDark}
        onShowOnboarding={startOnboarding}
        mobileProfileMenu={(
          <MobileProfileMenuItems
            profiles={profiles}
            activeId={activeProfileId}
            onSelect={handleSelectProfile}
            onNew={handleNewProfile}
            onManage={() => setManageOpen(true)}
            canCreate={profiles.length < 5}
            onUndo={handleUndo}
            canUndo={canUndo}
          />
        )}
        profilePicker={(
          <div className="flex items-center gap-2">
            <ProfileSwitcher
              profiles={profiles}
              activeId={activeProfileId}
              onSelect={handleSelectProfile}
              onNew={handleNewProfile}
              onManage={() => setManageOpen(true)}
              canCreate={profiles.length < 5}
            />
            {canUndo && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleUndo}
                aria-label="Undo last change"
                title="Revert settings and rules to the previous saved version"
              >
                Undo
              </Button>
            )}
          </div>
        )}
      />
      {tourActive && (
        <OnboardingTour
          stepIndex={tourStep}
          totalSteps={tourTotal}
          onNext={tourNext}
          onBack={tourBack}
          onGoTo={tourGoTo}
          onSkip={tourSkip}
          onStepPanel={setMobilePanel}
        />
      )}
      <MobilePanelTabBar
        active={mobilePanel}
        onChange={setMobilePanel}
        generateIsPending={generate.isPending}
      />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <div
          id="panel-settings"
          role="tabpanel"
          aria-label="Settings"
          className={mobilePanel === "settings" ? "contents lg:contents" : "hidden lg:contents"}
        >
          <SettingsPanel
            value={settings}
            onChange={setSettings}
          />
        </div>
        <div
          id="panel-rules"
          role="tabpanel"
          aria-label="Rules"
          className={mobilePanel === "rules" ? "contents lg:contents" : "hidden lg:contents"}
        >
          <RulesPanel
            canonicalRules={canonicalRules}
            positionRules={positionRules}
            onChange={setPositionRules}
            isError={rulesError}
            onRetry={refetchRules}
          />
        </div>
        <div
          id="panel-tiers"
          role="tabpanel"
          aria-label="Tiers"
          className={mobilePanel === "tiers" ? "contents lg:contents" : "hidden lg:contents"}
        >
          <TiersPanel
            result={generate.data ?? null}
            isPending={generate.isPending}
            isError={generate.isError}
            error={generate.error}
            isStale={isStale}
            onRegenerate={handleGenerate}
            canRegenerate={canGenerate}
            onDownloadXlsx={() => {
              // Return the promise (don't `void` it) so TiersPanel can await the
              // lazy chunk load + workbook build, show a busy spinner, and surface
              // a rejection as an inline error + Retry instead of swallowing it (#647).
              if (generate.data) {
                return downloadDraftXlsx(
                  generate.data.players,
                  settings.scoring_format,
                  activeProfile?.name ?? null,
                  resolvedTierNames,
                );
              }
            }}
            debugMode={debugMode}
            onDownloadDebugCsv={() => {
              if (generate.data) {
                downloadDebugCsv(
                  generate.data.players,
                  resolvedTierNames,
                );
              }
            }}
            scoringFormat={settings.scoring_format}
            tierLabelOverrides={resolvedTierNames}
            isFavoritePlayer={isFavoritePlayer}
            isFavoriteTeam={isFavoriteTeam}
            leagueKey={activeProfileId ?? "default"}
          />
        </div>
      </main>
      {/* Monetization: slim, dismissible sponsor strip. Renders nothing unless
          the deployment opts in via VITE_ADS_ENABLED (#387). */}
      <AdSlot slot={import.meta.env.VITE_ADSENSE_FOOTER_SLOT} />
      <ProfileManagerDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
        profiles={profiles}
        activeProfileId={activeProfileId}
        onRename={handleRenameProfile}
        onDelete={handleDeleteProfile}
      />
    </div>
  );
}
