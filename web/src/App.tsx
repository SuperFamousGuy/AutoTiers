import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useOnboarding } from "@/hooks/useOnboarding";
import { OnboardingTour } from "@/components/OnboardingTour";
import { ONBOARDING_STEPS } from "@/lib/onboardingSteps";
import { SettingsPanel, DEFAULT_FULL_SEASON_GAMES, DEFAULT_PRIOR_YEAR_RAMP, DEFAULT_TE_PREMIUM, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfilePicker } from "@/components/ProfilePicker";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import { MobilePanelTabBar, type MobilePanel } from "@/components/MobilePanelTabBar";
import { AdSlot } from "@/components/AdSlot";
import { PasswordResetPanel } from "@/components/PasswordResetPanel";
import { EmailVerificationBanner, shouldShowVerificationBanner, dismissVerificationBanner } from "@/components/EmailVerificationBanner";
import { NoProfileBanner } from "@/components/NoProfileBanner";
import { AuthDialog } from "@/components/AuthDialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useRules, useGenerateMutation, downloadDraftXlsx, downloadDebugCsv } from "@/api/hooks";
import { useAuth } from "@/contexts/AuthContext";
import { verifyEmail } from "@/api/auth";
import { createProfile, updateProfile, deleteProfile, activateProfile } from "@/api/profiles";
import { useAutoSave } from "@/hooks/useAutoSave";
import { describeGenerateError } from "@/lib/errors";
import { weightsAreValid } from "@/lib/weights";
import { buildResolvedTierNames, resolveTierLabelOverrides } from "@/lib/tiers";
import type { Rule, GenerateRequest, PositionRulesState } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "standard",
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
  const { user, profiles, setProfiles, refresh } = useAuth();
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
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [manageOpen, setManageOpen] = useState(false);
  const [linkedOpen, setLinkedOpen] = useState(false);
  const [linkingError, setLinkingError] = useState<string | null>(null);
  // Password-reset token extracted from ?reset_token= query param.
  const [resetToken, setResetToken] = useState<string | null>(null);
  // Controls the forgot-password dialog opened from the reset panel "Request new link" button.
  const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);
  // Email verification banner — shown until dismissed or email is verified.
  const [showVerifyBanner, setShowVerifyBanner] = useState(false);
  // Mobile panel state: "settings" when no result exists yet, "tiers" once a result exists.
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("settings");
  // Guard: auto-switch to Tiers only on the FIRST generate result after app load
  // (or after a profile switch). Reset to false on profile change so the next
  // generate result after switching profiles auto-switches again.
  const hasAutoSwitchedToTiers = useRef(false);
  // Per-profile undo history. Each entry is a snapshot of a moment when state
  // was committed to the server. Tip (last entry) is the current server state.
  // Undo pops the tip and re-PATCHes the prior tip, so undo also persists.
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

  // On first mount, read all query params (OAuth errors, password-reset token, verify token).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    // OAuth linking errors
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
    }

    // Password-reset token — show inline panel
    const rt = params.get("reset_token");
    if (rt) {
      setResetToken(rt);
    }

    // Email-verification token — call the endpoint immediately
    const vt = params.get("verify_token");
    if (vt) {
      verifyEmail(vt)
        .then(() => {
          refresh();
          toast({ title: "Email verified. Thank you!", variant: "success" });
        })
        .catch(() => {
          toast({
            title: "This verification link is invalid or has expired.",
            description: "You can request a new one from the banner below.",
            variant: "error",
          });
          // Surface the banner so the user can resend.
          setShowVerifyBanner(true);
        });
    }

    // Strip handled params from the URL.
    ["linking_error", "reset_token", "verify_token"].forEach((k) => params.delete(k));
    const rest = params.toString();
    window.history.replaceState({}, "", window.location.pathname + (rest ? `?${rest}` : ""));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On user change, set activeProfileId from the user's last-active.
  useEffect(() => {
    setActiveProfileId(user?.last_active_profile_id ?? null);
  }, [user]);

  // Show verification banner when user is logged in with unverified email.
  useEffect(() => {
    if (user && user.email && !user.email_verified && shouldShowVerificationBanner()) {
      setShowVerifyBanner(true);
    } else {
      setShowVerifyBanner(false);
    }
  }, [user]);

  // When activeProfileId changes, hydrate settings + positionRules from that profile.
  // Also seed undo history with the loaded snapshot — but only on the first
  // hydration for the profile, so existing in-memory history survives
  // profile-switch round-trips.
  useEffect(() => {
    if (!activeProfileId) return;
    const active = profiles.find((p) => p.id === activeProfileId);
    if (!active) return;

    setSettings(active.settings_json as unknown as SettingsState);
    // Profile rules_json is already in the new dict format (position-keyed overrides).
    // Backend guarantees dict format (model_validator migrates old list format to {}).
    setPositionRules(active.rules_json as unknown as PositionRulesState);
    setHistory((prev) => {
      if ((prev[activeProfileId]?.length ?? 0) > 0) return prev;
      return {
        ...prev,
        [activeProfileId]: [{
          settings_json: active.settings_json as Record<string, unknown>,
          rules_json: active.rules_json as unknown as Record<string, unknown>,
        }],
      };
    });
  }, [activeProfileId, profiles]);

  const autosavePayload = useMemo(() => ({
    settings_json: settings as unknown as Record<string, unknown>,
    rules_json: positionRules as unknown as Record<string, unknown>,
  }), [settings, positionRules]);

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
    await activateProfile(id);
  }, [generate.reset]);

  const handleNewProfile = useCallback(async () => {
    const created = await createProfile({
      name: `Profile ${profiles.length + 1}`,
      settings_json: settings as unknown as Record<string, unknown>,
      rules_json: positionRules as unknown as Record<string, Array<{ name: string; enabled: boolean; weight: number }>>,
    });
    setProfiles([...profiles, created]);
    setActiveProfileId(created.id);
    // Match the select-profile path: return to Settings, re-arm the auto-switch
    // guard, and clear the stale generate result so the new profile starts from
    // the empty state.
    setMobilePanel("settings");
    hasAutoSwitchedToTiers.current = false;
    generate.reset();
    setLastGeneratedRequest(null);
    await activateProfile(created.id);
  }, [profiles, settings, positionRules, setProfiles, generate.reset]);

  const handleRenameProfile = useCallback(async (id: string, name: string) => {
    const updated = await updateProfile(id, { name });
    setProfiles(profiles.map((p) => (p.id === id ? updated : p)));
  }, [profiles, setProfiles]);

  const handleDeleteProfile = useCallback(async (id: string) => {
    await deleteProfile(id);
    setProfiles((prev) => prev.filter((p) => p.id !== id));
    if (activeProfileId === id) {
      setActiveProfileId(null);
      // Deleting the active profile must mirror the select/new-profile reset:
      // clear the orphaned tier list (computed for a now-deleted profile),
      // return the mobile view to Settings, re-arm the auto-switch guard, and
      // drop the captured request so the staleness banner has nothing to
      // compare against. Without this the Tiers panel keeps rendering stale
      // tiers and Generate would fire with a silently wrong payload (#626).
      generate.reset();
      setLastGeneratedRequest(null);
      setMobilePanel("settings");
      hasAutoSwitchedToTiers.current = false;
    }
  }, [activeProfileId, setProfiles, generate.reset]);

  const handleUndo = useCallback(async () => {
    if (!activeProfileId) return;
    const current = history[activeProfileId];
    if (!current || current.length < 2) return;
    // Drop the current tip; the entry before it becomes the new tip.
    const trimmed = current.slice(0, -1);
    const newTip = trimmed[trimmed.length - 1];

    // Apply to local state immediately so the UI updates without waiting
    // for the server round-trip.
    setSettings(newTip.settings_json as unknown as SettingsState);
    setPositionRules(newTip.rules_json as unknown as PositionRulesState);

    // Drop the popped entry from history. The autosave guard ("bail if payload
    // matches tip") now blocks the debounced save from firing redundantly —
    // but the server still has the old tip, so we PATCH explicitly here.
    setHistory((prev) => ({ ...prev, [activeProfileId]: trimmed }));
    const updated = await updateProfile(activeProfileId, newTip);
    setProfiles(profiles.map((p) => (p.id === activeProfileId ? updated : p)));
  }, [activeProfileId, history, profiles, setProfiles]);

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
      te_premium_bonus: settings.te_premium_bonus,
      weight_prior_year: settings.weights.prior / 100,
      weight_espn: 0,
      weight_consensus: settings.weights.consensus / 100,
      full_season_games: settings.full_season_games,
      prior_year_ramp: settings.prior_year_ramp,
      draft_rounds: settings.draft_rounds,
      overall_tier_count: settings.tier_count ?? settings.league_size,
      rules: positionRules,
      keepers: linked?.keepers_json?.map((k) => k.player_name) ?? undefined,
      league_adp: linked?.adp_json ?? undefined,
    };
  };

  // Generate needs valid weights, loaded rules, and — when profiles exist — an
  // active profile. Deleting the active profile sets activeProfileId to null;
  // without this guard Generate would stay enabled and fire buildRequest() with
  // keepers/league_adp silently undefined (profiles.find returns undefined)
  // (#626). Logged-out users have no profiles, so they stay able to generate.
  const canGenerate =
    weightsAreValid(settings.weights) &&
    canonicalRules.length > 0 &&
    (profiles.length === 0 || activeProfileId !== null);

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
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={handleGenerate}
        currentState={{ settings, rules: positionRules }}
        isDark={isDark}
        onToggleDark={toggleDark}
        onShowOnboarding={startOnboarding}
        onOpenLinkedAccounts={user ? () => { setLinkingError(null); setLinkedOpen(true); } : undefined}
        activeProfileName={profiles.find((p) => p.id === activeProfileId)?.name ?? null}
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
      {/* Zero-profile banner — a logged-in user with no profile has autosave
          silently disabled, so warn them and offer a one-click fix (#606). */}
      {user && profiles.length === 0 && (
        <NoProfileBanner onCreateProfile={handleNewProfile} />
      )}
      {/* Email verification banner — shown below header when email is unverified */}
      {showVerifyBanner && user?.email && (
        <EmailVerificationBanner
          email={user.email}
          onDismiss={() => {
            dismissVerificationBanner();
            setShowVerifyBanner(false);
          }}
        />
      )}
      {/* Password-reset panel — replaces onboarding card slot when reset_token present */}
      {resetToken ? (
        <PasswordResetPanel
          token={resetToken}
          onDismiss={() => setResetToken(null)}
          onRequestNewLink={() => {
            setResetToken(null);
            setForgotPasswordOpen(true);
          }}
        />
      ) : (
        tourActive && (
          <OnboardingTour
            stepIndex={tourStep}
            totalSteps={tourTotal}
            onNext={tourNext}
            onBack={tourBack}
            onGoTo={tourGoTo}
            onSkip={tourSkip}
            onStepPanel={setMobilePanel}
          />
        )
      )}
      <MobilePanelTabBar
        active={mobilePanel}
        onChange={setMobilePanel}
        generateIsPending={generate.isPending}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] lg:grid-rows-1 overflow-hidden">
        <div
          id="panel-settings"
          role="tabpanel"
          aria-label="Settings"
          className={mobilePanel === "settings" ? "contents lg:contents" : "hidden lg:contents"}
        >
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
            keepers={
              profiles.find((p) => p.id === activeProfileId)?.linked_league?.keepers_json ?? undefined
            }
            scoringFormat={settings.scoring_format}
            tierLabelOverrides={resolvedTierNames}
            leagueKey={
              (() => {
                const active = profiles.find((p) => p.id === activeProfileId);
                // Prefer the linked league's id (stable across profile renames); fall
                // back to the profile id so unlinked profiles still get isolated Draft
                // Mode storage, then "default" if there's no active profile at all.
                return active?.linked_league?.league_id ?? active?.id ?? "default";
              })()
            }
          />
        </div>
      </main>
      {/* Monetization: slim, dismissible sponsor strip. Renders nothing unless
          the deployment opts in via VITE_ADS_ENABLED (#387). */}
      <AdSlot slot={import.meta.env.VITE_ADSENSE_FOOTER_SLOT} />
      <ManageProfilesDialog
        open={manageOpen}
        onOpenChange={setManageOpen}
        profiles={profiles}
        activeProfileId={activeProfileId}
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
          profiles={profiles}
          onSelectProfile={handleSelectProfile}
          onCreateProfile={handleNewProfile}
        />
      )}
      {/* Standalone forgot-password dialog — opened from the reset panel's "Request new link" */}
      <AuthDialog
        open={forgotPasswordOpen}
        onOpenChange={setForgotPasswordOpen}
        initialState={null}
        initialView="forgot_password"
      />
    </div>
  );
}
