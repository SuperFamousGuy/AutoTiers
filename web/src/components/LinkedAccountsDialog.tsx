import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { googleAuthorizeUrl, unlinkGoogle } from "@/api/auth";
import { ApiError } from "@/api/client";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { YahooConnectForm } from "@/components/YahooConnectForm";
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
  { id: "nfl", label: "NFL Fantasy", Icon: NflFantasyIcon, comingSoon: true },
  { id: "cbs", label: "CBS", Icon: CbsIcon, comingSoon: true },
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
      case "nfl":
      case "cbs": {
        const name = activeTab === "nfl" ? "NFL Fantasy" : "CBS Sports";
        return (
          <div className="space-y-1 py-6 text-center">
            <p className="text-sm font-medium">{name} — Coming Soon</p>
            <p className="text-xs text-muted-foreground">
              We're working on it. Check back next season.
            </p>
          </div>
        );
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-0 p-0">
        <div className="px-6 pt-6 pb-4">
          <DialogTitle>Connect Your League</DialogTitle>
          {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        </div>

        {/* Platform tab strip */}
        <div className="flex overflow-x-auto border-b border-border">
          {TABS.map(({ id, label, Icon, comingSoon }) => {
            const isConnected =
              (id === "yahoo" && !!user.yahoo_subject) ||
              (activeProfile?.linked_league?.provider === id);
            return (
              <button
                key={id}
                type="button"
                aria-label={label}
                disabled={comingSoon}
                onClick={() => setActiveTab(id)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-3 text-xs font-medium transition-colors",
                  activeTab === id
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
        <div className="px-6 py-4">{renderTabPanel()}</div>

        {/* Google footer — sign-in only, no fantasy league */}
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
      </DialogContent>
    </Dialog>
  );
}
