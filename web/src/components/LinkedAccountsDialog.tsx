import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
import { SleeperConnectForm } from "@/components/SleeperConnectForm";
import { EspnConnectForm } from "@/components/EspnConnectForm";
import { GoogleIcon, YahooIcon } from "@/components/BrandIcons";
import { FavoritesPanel } from "@/components/FavoritesPanel";
import { useFavorites } from "@/hooks/useFavorites";
import { searchPlayers } from "@/api/favorites";
import type { User, Profile } from "@/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null;
  onRefresh: () => Promise<void>;
  initialError: string | null;
  activeProfile?: Profile | null;
}

export function LinkedAccountsDialog({ open, onOpenChange, user, onRefresh, initialError, activeProfile }: Props) {
  const [error, setError] = useState<string | null>(initialError);
  const [busy, setBusy] = useState<"google" | "yahoo" | null>(null);
  const [activeForm, setActiveForm] = useState<"sleeper" | "espn" | null>(null);

  const { favorites, save: saveFavorites } = useFavorites(user !== null);

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
    // Full-page navigation; OAuth callback brings us back. intent=link tells
    // the backend we're attaching to the current account — if the session
    // cookie fails to make the round-trip the user gets a clear error
    // instead of being silently signed in as a brand-new account.
    const base = provider === "google" ? googleAuthorizeUrl() : yahooAuthorizeUrl();
    window.location.href = `${base}?intent=link`;
  }

  const linkedAccountsContent = (
    <>
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
      ) : user !== null ? (
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
      ) : null}
    </>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Linked Accounts</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        {user !== null ? (
          <Tabs defaultValue="accounts">
            <TabsList>
              <TabsTrigger value="accounts">Accounts</TabsTrigger>
              <TabsTrigger value="favorites">Favorites</TabsTrigger>
            </TabsList>
            <TabsContent value="accounts">
              {linkedAccountsContent}
            </TabsContent>
            <TabsContent value="favorites">
              <FavoritesPanel
                favorites={favorites}
                onSave={saveFavorites}
                searchPlayers={searchPlayers}
              />
            </TabsContent>
          </Tabs>
        ) : (
          linkedAccountsContent
        )}
      </DialogContent>
    </Dialog>
  );
}
