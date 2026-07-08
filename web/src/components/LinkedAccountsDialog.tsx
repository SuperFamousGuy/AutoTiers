import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  googleAuthorizeUrl,
  unlinkGoogle,
  yahooAuthorizeUrl,
  unlinkYahoo,
} from "@/api/auth";
import { ApiError } from "@/api/client";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { YahooConnectForm } from "@/components/YahooConnectForm";
import { CbsConnectForm } from "@/components/CbsConnectForm";
import { NflConnectForm } from "@/components/NflConnectForm";
import { PasswordManagementSection } from "@/components/PasswordManagementSection";
import {
  GoogleIcon,
  YahooIcon,
  SleeperIcon,
  EspnIcon,
  NflFantasyIcon,
  CbsIcon,
} from "@/components/BrandIcons";
import { cn } from "@/lib/utils";
import type { User, Profile } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  onRefresh: () => Promise<void>;
  initialError: string | null;
  activeProfile?: Profile | null;
}

type PlatformTab = "sleeper" | "espn" | "yahoo" | "nfl" | "cbs";

const TABS: {
  id: PlatformTab;
  label: string;
  Icon: () => React.JSX.Element;
  comingSoon?: boolean;
}[] = [
  { id: "sleeper", label: "Sleeper", Icon: SleeperIcon },
  { id: "espn", label: "ESPN", Icon: EspnIcon },
  { id: "yahoo", label: "Yahoo", Icon: YahooIcon },
  { id: "nfl", label: "NFL Fantasy", Icon: NflFantasyIcon },
  { id: "cbs", label: "CBS", Icon: CbsIcon },
];

export function LinkedAccountsDialog({
  open,
  onOpenChange,
  user,
  onRefresh,
  initialError,
  activeProfile,
}: Props) {
  const [error, setError] = useState<string | null>(initialError);
  const [activeTab, setActiveTab] = useState<PlatformTab>("sleeper");
  const [googleBusy, setGoogleBusy] = useState(false);
  const [yahooBusy, setYahooBusy] = useState(false);
  const tabRefs = useRef<Partial<Record<PlatformTab, HTMLButtonElement | null>>>({});

  // WAI-ARIA APG tab pattern: Left/Right move focus and selection between
  // enabled tabs, wrapping at the ends and skipping disabled ("coming soon")
  // ones. Selection follows focus, matching the automatic-activation variant.
  function handleTabKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const enabled = TABS.filter((t) => !t.comingSoon);
    const currentIdx = enabled.findIndex((t) => t.id === activeTab);
    if (currentIdx === -1) return;
    e.preventDefault();
    const delta = e.key === "ArrowRight" ? 1 : -1;
    const next = enabled[(currentIdx + delta + enabled.length) % enabled.length];
    setActiveTab(next.id);
    tabRefs.current[next.id]?.focus();
  }

  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  useEffect(() => {
    if (!open) setActiveTab("sleeper");
  }, [open]);

  async function handleGoogleDisconnect() {
    setError(null);
    setGoogleBusy(true);
    try {
      await unlinkGoogle();
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed. Please try again.");
    } finally {
      setGoogleBusy(false);
    }
  }

  function handleGoogleConnect() {
    window.location.href = `${googleAuthorizeUrl()}?intent=link`;
  }

  async function handleYahooDisconnect() {
    setError(null);
    setYahooBusy(true);
    try {
      await unlinkYahoo();
      await onRefresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed. Please try again.");
    } finally {
      setYahooBusy(false);
    }
  }

  function handleYahooConnect() {
    window.location.href = `${yahooAuthorizeUrl()}?intent=link`;
  }

  function renderTabPanel() {
    // Sleeper and ESPN need an active profile for their API calls.
    if ((activeTab === "sleeper" || activeTab === "espn") && !activeProfile) {
      return (
        <p className="py-4 text-center text-xs text-muted-foreground">
          Select a profile above to connect a fantasy league.
        </p>
      );
    }

    switch (activeTab) {
      case "sleeper":
        return (
          <SleeperConnectForm
            profile={activeProfile!}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "espn":
        return (
          <EspnConnectForm
            profile={activeProfile!}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "yahoo":
        if (!activeProfile) {
          return (
            <p className="py-4 text-center text-xs text-muted-foreground">
              Select a profile above to connect a fantasy league.
            </p>
          );
        }
        return (
          <YahooConnectForm
            profile={activeProfile}
            user={user}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "cbs":
        if (!activeProfile) {
          return (
            <p className="py-4 text-center text-xs text-muted-foreground">
              Select a profile above to connect a fantasy league.
            </p>
          );
        }
        return (
          <CbsConnectForm
            profile={activeProfile}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
      case "nfl":
        if (!activeProfile) {
          return (
            <p className="py-4 text-center text-xs text-muted-foreground">
              Select a profile above to connect a fantasy league.
            </p>
          );
        }
        return (
          <NflConnectForm
            profile={activeProfile}
            onLinked={() => onRefresh()}
            onRefresh={onRefresh}
          />
        );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0">
        <div className="px-6 pt-6 pb-4">
          <DialogTitle>Connect Your League</DialogTitle>
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>

        {/* Account section — password + Google sign-in */}
        <div className="border-b border-border">
          <div className="px-4 pb-1 pt-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Account
            </p>
          </div>

          {/* Password row */}
          <PasswordManagementSection user={user} onRefresh={onRefresh} />

          {/* Google row — sign-in only */}
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <GoogleIcon />
              Google · Sign-in only, no fantasy league
            </span>
            {user.google_subject ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                disabled={googleBusy}
                aria-label="Disconnect Google"
                onClick={handleGoogleDisconnect}
              >
                Unlink
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                aria-label="Link Google"
                onClick={handleGoogleConnect}
              >
                Link
              </Button>
            )}
          </div>

          {/* Yahoo row — sign-in identity (fantasy leagues are linked in the tab below) */}
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <YahooIcon />
              Yahoo · Sign-in identity
            </span>
            {user.yahoo_subject ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                disabled={yahooBusy}
                aria-label="Disconnect Yahoo"
                onClick={handleYahooDisconnect}
              >
                Unlink
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                aria-label="Link Yahoo"
                onClick={handleYahooConnect}
              >
                Link
              </Button>
            )}
          </div>
        </div>

        {/* Fantasy leagues section */}
        <div className="px-4 pb-1 pt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Fantasy leagues
          </p>
        </div>

        {/* Platform tab strip */}
        <div
          role="tablist"
          aria-label="Fantasy platform"
          onKeyDown={handleTabKeyDown}
          className="flex overflow-x-auto border-b border-border"
        >
          {TABS.map(({ id, label, Icon, comingSoon }) => {
            // Green dot means the same thing for every provider: an active league
            // is linked to this profile. Yahoo's account-level OAuth status (signed
            // in, no league yet) is surfaced inside the Yahoo tab panel instead — see
            // YahooConnectForm — so the tab strip never over-promises "connected".
            const isConnected = activeProfile?.linked_league?.provider === id;
            const selected = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                id={`tab-${id}`}
                aria-label={label}
                aria-selected={selected}
                aria-controls="linked-accounts-tabpanel"
                tabIndex={selected ? 0 : -1}
                ref={(el) => {
                  tabRefs.current[id] = el;
                }}
                disabled={comingSoon}
                onClick={() => setActiveTab(id)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-3 text-xs font-medium transition-colors",
                  selected
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                  comingSoon && "cursor-not-allowed opacity-40",
                )}
              >
                <Icon />
                {label}
                {isConnected && (
                  <span className="ml-0.5 h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
                )}
                {comingSoon && <span className="ml-0.5 text-[10px] font-normal">(soon)</span>}
              </button>
            );
          })}
        </div>

        {/* Tab panel */}
        <div
          role="tabpanel"
          id="linked-accounts-tabpanel"
          aria-labelledby={`tab-${activeTab}`}
          className="px-6 py-4"
        >
          {renderTabPanel()}
        </div>
      </DialogContent>
    </Dialog>
  );
}
