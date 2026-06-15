import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { Header } from "@/components/Header";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useOnboarding } from "@/hooks/useOnboarding";
import { OnboardingCard } from "@/components/OnboardingCard";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { ProfilePicker } from "@/components/ProfilePicker";
import { ManageProfilesDialog } from "@/components/ManageProfilesDialog";
import { LinkedAccountsDialog } from "@/components/LinkedAccountsDialog";
import { MobilePanelTabBar, type MobilePanel } from "@/components/MobilePanelTabBar";
import { PasswordResetPanel } from "@/components/PasswordResetPanel";
import { EmailVerificationBanner, shouldShowVerificationBanner, dismissVerificationBanner } from "@/components/EmailVerificationBanner";
import { AuthDialog } from "@/components/AuthDialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useRules, useGenerateMutation, downloadCsv } from "@/api/hooks";
import { useAuth } from "@/contexts/AuthContext";
import { verifyEmail } from "@/api/auth";
import { createProfile, updateProfile, deleteProfile, activateProfile } from "@/api/profiles";
import { useAutoSave } from "@/hooks/useAutoSave";
import { weightsAreValid } from "@/lib/weights";
import { buildResolvedTierNames } from "@/lib/tiers";
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
  weights: { prior: 30, consensus: 70 },
};

export default function App() {
  const [isDark, toggleDark] = useDarkMode();
  const { showOnboarding, dismiss: dismissOnboarding, reopen: reopenOnboarding } = useOnboarding();
  const { user, profiles, setProfiles, refresh } = useAuth();
  const { toast } = useToast();
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
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

  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

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
    await activateProfile(created.id);
  }, [profiles, settings, positionRules, setProfiles, generate.reset]);

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
      weight_prior_year: settings.weights.prior / 100,
      weight_espn: 0,
      weight_consensus: settings.weights.consensus / 100,
      draft_rounds: settings.draft_rounds,
      overall_tier_count: settings.tier_count ?? settings.league_size,
      rules: positionRules,
      keepers: linked?.keepers_json?.map((k) => k.player_name) ?? undefined,
      league_adp: linked?.adp_json ?? undefined,
    };
  };

  const canGenerate = weightsAreValid(settings.weights) && canonicalRules.length > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={() => generate.mutate(buildRequest())}
        currentState={{ settings, rules: positionRules }}
        isDark={isDark}
        onToggleDark={toggleDark}
        onShowOnboarding={reopenOnboarding}
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
        showOnboarding && <OnboardingCard onDismiss={dismissOnboarding} />
      )}
      <MobilePanelTabBar active={mobilePanel} onChange={setMobilePanel} />
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
            onDownloadCsv={() => {
              if (generate.data) {
                downloadCsv(
                  generate.data.players,
                  buildResolvedTierNames(
                    settings.tier_count ?? settings.league_size,
                    settings.tier_labels,
                  ),
                );
              }
            }}
            keepers={
              profiles.find((p) => p.id === activeProfileId)?.linked_league?.keepers_json ?? undefined
            }
            scoringFormat={settings.scoring_format}
            tierLabelOverrides={buildResolvedTierNames(
              settings.tier_count ?? settings.league_size,
              settings.tier_labels,
            )}
          />
        </div>
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
