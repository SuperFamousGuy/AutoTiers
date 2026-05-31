import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { GoogleIcon, YahooIcon } from "@/components/BrandIcons";
import type { User, Profile } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  onRefresh: () => Promise<void>;
  initialError: string | null;
  activeProfile?: Profile | null;
}

export function LinkedAccountsDialog({ open, onOpenChange, user, onRefresh, initialError, activeProfile }: Props) {
  const [error, setError] = useState<string | null>(initialError);
  const [busy, setBusy] = useState<"google" | "yahoo" | null>(null);
  const [activeForm, setActiveForm] = useState<"sleeper" | "espn" | null>(null);

  // Refresh local error when initialError prop changes (e.g. dialog reopened with new error).
  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  // Reset the connect-form state whenever the dialog closes so it doesn't
  // come back open mid-form.
  useEffect(() => {
    if (!open) setActiveForm(null);
  }, [open]);

  async function handleDisconnect(provider: "google" | "yahoo") {
    setError(null);
    setBusy(provider);
    try {
      if (provider === "google") await unlinkGoogle();
      else await unlinkYahoo();
      await onRefresh();
    } catch (e) {
      if (e instanceof ApiError) setError(e.message);
      else setError("Disconnect failed. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  function handleConnect(provider: "google" | "yahoo") {
    // Full-page navigation; OAuth callback brings us back.
    window.location.href = provider === "google" ? googleAuthorizeUrl() : yahooAuthorizeUrl();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Linked Accounts</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        {activeForm === "sleeper" && activeProfile ? (
          <SleeperConnectForm
            profileId={activeProfile.id}
            onLinked={async () => { setActiveForm(null); await onRefresh(); }}
            onCancel={() => setActiveForm(null)}
          />
        ) : activeForm === "espn" && activeProfile ? (
          <EspnConnectForm
            profileId={activeProfile.id}
            onLinked={async () => { setActiveForm(null); await onRefresh(); }}
            onCancel={() => setActiveForm(null)}
          />
        ) : (
          <>
            <ul className="space-y-3">
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm"><GoogleIcon />Google</span>
                {user.google_subject ? (
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="Disconnect Google"
                    disabled={busy === "google"}
                    onClick={() => handleDisconnect("google")}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => handleConnect("google")}>
                    Connect
                  </Button>
                )}
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm"><YahooIcon />Yahoo</span>
                {user.yahoo_subject ? (
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="Disconnect Yahoo"
                    disabled={busy === "yahoo"}
                    onClick={() => handleDisconnect("yahoo")}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => handleConnect("yahoo")}>
                    Connect
                  </Button>
                )}
              </li>
            </ul>
            {activeProfile && (
              <LinkedLeagueSection
                profile={activeProfile}
                onChanged={onRefresh}
                onConnectSleeper={() => setActiveForm("sleeper")}
                onConnectEspn={() => setActiveForm("espn")}
              />
            )}
            {!activeProfile && (
              <p className="text-xs text-muted-foreground mt-3">
                Select a profile to link a fantasy league.
              </p>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
