import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { googleAuthorizeUrl, yahooAuthorizeUrl, unlinkGoogle, unlinkYahoo } from "@/api/auth";
import { ApiError } from "@/api/client";
import { LinkedLeagueSection } from "@/components/LinkedLeagueSection";
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

  // Refresh local error when initialError prop changes (e.g. dialog reopened with new error).
  useEffect(() => {
    setError(initialError);
  }, [initialError]);

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
        <DialogTitle>Linked accounts</DialogTitle>
        {error && <p className="text-xs text-red-600 mb-2">{error}</p>}
        <ul className="space-y-3">
          <li className="flex items-center justify-between">
            <span className="text-sm">Email</span>
            <span className="text-sm text-muted-foreground">
              {user.email ?? "Not set"}
            </span>
          </li>
          <li className="flex items-center justify-between">
            <span className="text-sm">Google</span>
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
            <span className="text-sm">Yahoo</span>
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
          <LinkedLeagueSection profile={activeProfile} onChanged={onRefresh} />
        )}
        {!activeProfile && (
          <p className="text-xs text-muted-foreground border-t pt-4 mt-4">
            Select a profile to link a fantasy league.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
